from __future__ import annotations

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
import yaml

from .logging import RunLog
from .scope import Scope
from .tasks import Task
from .tmux import TmuxSession


class OrchestratorError(RuntimeError):
    pass


@dataclass
class AgentConfig:
    default_image: str
    session_prefix: str = "bb"
    workspace_mount: str = "$PWD:/workspace"
    require_scope: bool = True
    provider: str = "openrouter"
    model: str = "anthropic/claude-sonnet-4.5"

    @classmethod
    def load(cls, path: str | Path) -> "AgentConfig":
        raw = yaml.safe_load(Path(path).read_text()) or {}
        runtime = raw.get("runtime", {}) or {}
        model = raw.get("model", {}) or {}
        return cls(
            default_image=runtime.get("default_image", "nwodtuhs/exegol:free"),
            session_prefix=runtime.get("session_prefix", "bb"),
            workspace_mount=runtime.get("workspace_mount", "$PWD:/workspace"),
            require_scope=bool(runtime.get("require_scope", True)),
            provider=model.get("provider", "openrouter"),
            model=model.get("default_model", "anthropic/claude-sonnet-4.5"),
        )


def render_system_prompt(scope: Scope, task: Task) -> str:
    return f"""You are a legal bug bounty / vulnerability research assistant.

Hard operating rules:
- Work only on explicitly authorized targets in the scope brief.
- Prefer passive analysis, code review, safe local reproduction, and low-volume checks.
- Never perform denial of service, stealth, persistence, credential theft, credential stuffing, destructive changes, or data exfiltration.
- Do not broaden scope, pivot to third parties, or scan the public internet.
- Before any state-changing action, write a note explaining risk and wait for human approval.
- Keep reproducible evidence and a concise timeline.

{scope.render_agent_brief(task.target)}

{task.render()}
"""


def write_pi_prompt(run: RunLog, scope: Scope, task: Task) -> Path:
    prompt = render_system_prompt(scope, task)
    return run.write_markdown("prompt.md", prompt)


def docker_pi_command(image: str, prompt_file: Path, workspace_mount: str, *, provider: str, model: str) -> str:
    # We keep this as a transparent shell command rather than hiding it behind a custom DSL.
    mount = os.path.expandvars(workspace_mount)
    # Assumes pi is installed in the image or via my-resources; fallback starts a shell with the prompt visible.
    quoted_prompt = shlex.quote(str(prompt_file))
    run_name = shlex.quote(prompt_file.parent.name)
    return (
        f"docker run --rm -it --name bb-{prompt_file.parent.name} "
        f"--network host -v {shlex.quote(mount)} -e OPENROUTER_API_KEY -e OPENROUTER_SITE_URL -e OPENROUTER_APP_NAME "
        f"{shlex.quote(image)} bash -lc "
        + shlex.quote(
            "cd /workspace && "
            "if command -v pi >/dev/null 2>&1; then "
            f"pi --provider {shlex.quote(provider)} --model {shlex.quote(model)} --name {run_name} @{quoted_prompt}; "
            "else echo 'Pi is not installed in this container. Install it or use docker/controller.Dockerfile.'; "
            f"echo 'Prompt:'; cat {quoted_prompt}; exec bash; fi"
        )
    )


def start_recorder(run: RunLog, session_name: str, window_name: str) -> int:
    """Spawn a detached background process tailing the tmux window into transcript.log.

    Detached (start_new_session) so it outlives this CLI invocation and keeps
    recording for as long as the launched window exists.
    """
    cmd = [sys.executable, "-m", "bbagent.cli", "record", str(run.dir), session_name, window_name]
    log_file = (run.dir / "recorder.out").open("w")
    proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, start_new_session=True)
    (run.dir / "recorder.pid").write_text(str(proc.pid))
    return proc.pid


def launch_task(task_path: str, config_path: str, *, no_docker: bool = False, record: bool = True) -> dict[str, str]:
    task = Task.load(task_path)
    scope_path = Path(task.scope)
    if not scope_path.exists():
        # Resolve task-relative scope path.
        scope_path = Path(task_path).resolve().parent.parent / task.scope
    scope = Scope.load(scope_path)
    scope.target(task.target)
    cfg = AgentConfig.load(config_path)
    run = RunLog(scope.out_dir)
    prompt = write_pi_prompt(run, scope, task)
    run.write("task_loaded", f"Loaded task {task.id}", {"task": task_path, "scope": str(scope.path)})

    session = TmuxSession(f"{cfg.session_prefix}-{scope.program}")
    window_name = task.id[:24]
    if no_docker:
        cmd = f"bash -lc 'cat {shlex.quote(str(prompt))}; echo; echo Ready for manual Pi run; exec bash'"
    else:
        cmd = docker_pi_command(cfg.default_image, prompt, cfg.workspace_mount, provider=cfg.provider, model=cfg.model)
    session.new_window(window_name, cmd)
    run.write("tmux_window_started", f"Started tmux window {window_name}", {"session": session.name, "run_id": run.run_id})

    info = {
        "run_id": run.run_id,
        "session": session.name,
        "window": window_name,
        "prompt": str(prompt),
        "events": str(run.events_path),
    }
    if record:
        recorder_pid = start_recorder(run, session.name, window_name)
        run.write("recorder_started", f"Started background recorder pid={recorder_pid}")
        info["transcript"] = str(run.dir / "transcript.log")
    return info


def run_shell_checked(command: list[str]) -> str:
    cp = subprocess.run(command, text=True, capture_output=True)
    if cp.returncode != 0:
        raise OrchestratorError(cp.stderr or cp.stdout)
    return cp.stdout
