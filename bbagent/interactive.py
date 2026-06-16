from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

from .harbor_export import export_task_to_harbor, slugify


class InteractiveError(RuntimeError):
    pass


def _read_network_mode(task_dir: Path) -> str:
    task_toml = task_dir / "task.toml"
    if not task_toml.exists():
        return "bridge"
    text = task_toml.read_text(errors="replace")
    match = re.search(r'^network_mode\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        return "bridge"
    mode = match.group(1)
    if mode == "no-network":
        return "none"
    # Docker has no simple hostname allowlist equivalent. Use the default bridge network for
    # interactive sessions; Harbor remains the stricter runner for eval/RL.
    return "bridge"


def resolve_interactive_task(
    task_or_dir: str | Path,
    *,
    out_dir: str | Path = "benchmarks/flaggy",
    force: bool = False,
    base_image: str = "python:3.12-slim",
) -> Path:
    path = Path(task_or_dir)
    if path.is_file():
        return export_task_to_harbor(path, out_dir, force=force, base_image=base_image)
    if path.is_dir() and (path / "task.toml").exists() and (path / "environment" / "Dockerfile").exists():
        return path.resolve()
    raise InteractiveError(
        f"Expected a Flaggy task YAML or Harbor task directory with task.toml + environment/Dockerfile: {path}"
    )


def interactive_command(task_dir: Path, *, tool: str = "shell", image_tag: str | None = None) -> list[str]:
    if not shutil.which("docker"):
        raise InteractiveError("docker is not installed or not on PATH")
    task_dir = task_dir.resolve()
    env_dir = task_dir / "environment"
    if not (env_dir / "Dockerfile").exists():
        raise InteractiveError(f"Missing environment/Dockerfile in {task_dir}")
    tag = image_tag or f"flaggy-interactive-{slugify(task_dir.name)}"
    logs_dir = task_dir / ".interactive" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    instruction = task_dir / "instruction.md"
    network = _read_network_mode(task_dir)

    if tool not in {"shell", "pi"}:
        raise InteractiveError("--tool must be 'shell' or 'pi'")

    if tool == "pi":
        inner = (
            "mkdir -p /logs/artifacts/evidence; "
            "echo 'Instruction: /app/instruction.md'; "
            "echo 'Artifacts: /logs/artifacts'; "
            "if command -v pi >/dev/null 2>&1; then "
            "pi @/app/instruction.md; "
            "else echo 'Pi is not installed in this image. Dropping to bash in the same task environment.'; "
            "exec bash; fi"
        )
    else:
        inner = (
            "mkdir -p /logs/artifacts/evidence; "
            "echo 'Instruction: /app/instruction.md'; "
            "echo 'Artifacts: /logs/artifacts'; "
            "echo 'Run commands manually, or install/use Pi inside this container.'; "
            "exec bash"
        )

    build = ["docker", "build", "-t", tag, str(env_dir)]
    run = [
        "docker",
        "run",
        "--rm",
        "-it",
        "--network",
        network,
        "-v",
        f"{logs_dir}:/logs",
        "-v",
        f"{instruction}:/app/instruction.md:ro",
        "-e",
        f"FLAGGY_INTERACTIVE_TOOL={tool}",
        tag,
        "bash",
        "-lc",
        inner,
    ]
    return ["bash", "-lc", shlex.join(build) + " && " + shlex.join(run)]


def run_interactive(
    task_or_dir: str | Path,
    *,
    out_dir: str | Path = "benchmarks/flaggy",
    force: bool = False,
    base_image: str = "python:3.12-slim",
    tool: str = "shell",
    image_tag: str | None = None,
) -> int:
    task_dir = resolve_interactive_task(
        task_or_dir,
        out_dir=out_dir,
        force=force,
        base_image=base_image,
    )
    cmd = interactive_command(task_dir, tool=tool, image_tag=image_tag)
    return subprocess.call(cmd)
