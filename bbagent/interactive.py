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


def interactive_command(
    task_dir: Path,
    *,
    tool: str = "shell",
    image_tag: str | None = None,
    image: str | None = None,
) -> list[str]:
    if not shutil.which("docker"):
        raise InteractiveError("docker is not installed or not on PATH")
    task_dir = task_dir.resolve()
    env_dir = task_dir / "environment"
    logs_dir = task_dir / ".interactive" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    instruction = task_dir / "instruction.md"
    network = _read_network_mode(task_dir)

    if tool not in {"shell", "pi"}:
        raise InteractiveError("--tool must be 'shell' or 'pi'")

    # Two modes:
    #   * default: build the task's environment/Dockerfile (workdir files are
    #     baked into the image via COPY).
    #   * --image: reuse a prebuilt image (e.g. the Exegol-based operator image)
    #     and mount the task's workdir so its files are present without a rebuild.
    extra_mounts: list[str] = []
    if image:
        run_image = image
        build: list[str] | None = None
        workdir = env_dir / "workdir"
        if workdir.exists():
            extra_mounts = ["-v", f"{workdir}:/app"]
    else:
        if not (env_dir / "Dockerfile").exists():
            raise InteractiveError(f"Missing environment/Dockerfile in {task_dir}")
        run_image = image_tag or f"flaggy-interactive-{slugify(task_dir.name)}"
        build = ["docker", "build", "-t", run_image, str(env_dir)]

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

    run = [
        "docker",
        "run",
        "--rm",
        "-it",
        "--network",
        network,
        *extra_mounts,
        "-v",
        f"{logs_dir}:/logs",
        "-v",
        f"{instruction}:/app/instruction.md:ro",
        "-e",
        f"FLAGGY_INTERACTIVE_TOOL={tool}",
        run_image,
        "bash",
        "-lc",
        inner,
    ]
    if build is None:
        return ["bash", "-lc", shlex.join(run)]
    return ["bash", "-lc", shlex.join(build) + " && " + shlex.join(run)]


def run_interactive(
    task_or_dir: str | Path,
    *,
    out_dir: str | Path = "benchmarks/flaggy",
    force: bool = False,
    base_image: str = "python:3.12-slim",
    tool: str = "shell",
    image_tag: str | None = None,
    image: str | None = None,
) -> int:
    task_dir = resolve_interactive_task(
        task_or_dir,
        out_dir=out_dir,
        force=force,
        base_image=base_image,
    )
    cmd = interactive_command(task_dir, tool=tool, image_tag=image_tag, image=image)
    return subprocess.call(cmd)
