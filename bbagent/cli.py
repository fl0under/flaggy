from __future__ import annotations

import argparse
from pathlib import Path
import sys

from rich.console import Console

from .harbor_export import HarborExportError, export_task_to_harbor
from .interactive import InteractiveError, run_interactive
from .scope import Scope, ScopeError

console = Console()


def cmd_check(args: argparse.Namespace) -> int:
    try:
        scope = Scope.load(args.scope)
    except ScopeError as exc:
        console.print(f"[red]Scope error:[/red] {exc}")
        return 2
    console.print(f"[green]Scope OK[/green] — {scope.program} ({scope.mode})")
    for target in scope.allowed_targets:
        console.print(f"  • ({target.kind}) {target.name}: {target.locator()}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    try:
        path = export_task_to_harbor(
            args.task,
            args.out,
            docker_image=args.docker_image,
            base_image=args.base_image,
            force=args.force,
        )
    except (HarborExportError, ScopeError, Exception) as exc:
        console.print(f"[red]Export failed:[/red] {exc}")
        return 1
    try:
        rel = path.relative_to(Path.cwd())
    except ValueError:
        rel = path
    console.print(f"[green]Harbor task written[/green]: {rel}")
    console.print("Run with Harbor directly:")
    print(f"  harbor run -p {rel} -a terminus-2 -m <model>")
    console.print("Open the same environment interactively:")
    print(f"  flaggy interactive {rel}")
    return 0


def cmd_interactive(args: argparse.Namespace) -> int:
    try:
        return run_interactive(
            args.task_or_dir,
            out_dir=args.out,
            force=args.force,
            base_image=args.base_image,
            tool=args.tool,
            image_tag=args.image_tag,
            image=args.image,
        )
    except (InteractiveError, HarborExportError, ScopeError, Exception) as exc:
        console.print(f"[red]Interactive launch failed:[/red] {exc}")
        return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="flaggy",
        description="Tiny Harbor-first helper for scoped security-research eval tasks.",
    )
    sub = p.add_subparsers(required=True)

    c = sub.add_parser("check", help="Validate a scope file")
    c.add_argument("scope")
    c.set_defaults(func=cmd_check)

    e = sub.add_parser("export", help="Export a Flaggy task YAML into a native Harbor task directory")
    e.add_argument("task")
    e.add_argument("--out", default="benchmarks/flaggy")
    e.add_argument("--docker-image", help="Set [environment].docker_image instead of relying only on the generated Dockerfile")
    e.add_argument("--base-image", default="python:3.12-slim", help="Base image for generated environment/Dockerfile")
    e.add_argument("--force", action="store_true", help="Overwrite an existing generated Harbor task")
    e.set_defaults(func=cmd_export)

    i = sub.add_parser(
        "interactive",
        help="Open the same generated Harbor environment in Docker for manual/Pi-assisted work",
    )
    i.add_argument("task_or_dir", help="Flaggy task YAML or generated Harbor task directory")
    i.add_argument("--out", default="benchmarks/flaggy", help="Export destination when task_or_dir is a YAML task")
    i.add_argument("--force", action="store_true", help="Re-export if task_or_dir is a YAML task and the Harbor task exists")
    i.add_argument("--base-image", default="python:3.12-slim", help="Base image used if exporting first")
    i.add_argument("--tool", choices=["shell", "pi"], default="shell", help="Start a shell, or try Pi and fall back to shell")
    i.add_argument("--image-tag", help="Docker tag for the image built from the task's environment/Dockerfile")
    i.add_argument("--image", help="Use a prebuilt image (e.g. flaggy-operator:latest) instead of building the task Dockerfile; the task workdir is mounted at /app")
    i.set_defaults(func=cmd_interactive)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
