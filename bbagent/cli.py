from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from rich.console import Console
from rich.table import Table

from .llm import OpenRouterClient, OpenRouterConfig
from .orchestrator import launch_task, render_system_prompt
from .scope import Scope, ScopeError
from .tasks import Task
from .tmux import TmuxError, TmuxSession

console = Console()


def cmd_scope_check(args: argparse.Namespace) -> int:
    try:
        scope = Scope.load(args.scope)
    except ScopeError as exc:
        console.print(f"[red]Scope error:[/red] {exc}")
        return 2
    console.print(f"[green]Scope OK[/green] — {scope.program} ({scope.mode})")
    for t in scope.allowed_targets:
        console.print(f"  • ({t.kind}) {t.name}: {t.locator()}")
    return 0


def cmd_prompt(args: argparse.Namespace) -> int:
    task = Task.load(args.task)
    scope_path = Path(task.scope)
    if not scope_path.exists():
        scope_path = Path(args.task).resolve().parent.parent / task.scope
    scope = Scope.load(scope_path)
    console.print(render_system_prompt(scope, task))
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    task = Task.load(args.task)
    scope_path = Path(task.scope)
    if not scope_path.exists():
        scope_path = Path(args.task).resolve().parent.parent / task.scope
    scope = Scope.load(scope_path)
    target = scope.target(task.target)
    model = args.model or os.environ.get("BB_MODEL", "anthropic/claude-sonnet-4.5")
    client = OpenRouterClient(OpenRouterConfig(model=model))
    system = render_system_prompt(scope, task)
    user = (
        "Create a safe, legal, non-destructive work plan for this task. "
        "Use numbered steps, include stopping points for human approval, and avoid exploit instructions. "
        f"Target ({target.kind}): {target.locator()}"
    )
    result = client.chat([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ])
    console.print(result)
    return 0


def cmd_launch(args: argparse.Namespace) -> int:
    try:
        info = launch_task(args.task, args.config, no_docker=args.no_docker)
    except (ScopeError, TmuxError, Exception) as exc:  # broad by design: CLI should print readable failure
        console.print(f"[red]Launch failed:[/red] {exc}")
        return 1
    console.print("[green]Started[/green]")
    for k, v in info.items():
        console.print(f"{k}: {v}")
    console.print(f"Attach with: tmux attach -t {info['session']}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    session = TmuxSession(args.session)
    try:
        windows = session.list_windows()
    except TmuxError as exc:
        console.print(f"[red]tmux error:[/red] {exc}")
        return 1
    table = Table(title=f"tmux session {args.session}")
    table.add_column("index")
    table.add_column("name")
    table.add_column("command")
    table.add_column("pid")
    for w in windows:
        table.add_row(w["index"], w["name"], w["command"], w["pid"])
    console.print(table)
    return 0


def cmd_tail(args: argparse.Namespace) -> int:
    session = TmuxSession(args.session)
    try:
        console.print(session.capture(args.window, lines=args.lines))
    except TmuxError as exc:
        console.print(f"[red]tmux error:[/red] {exc}")
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bbctl", description="Prototype controller for scoped Pi bounty agents")
    sub = p.add_subparsers(required=True)

    s = sub.add_parser("scope-check", help="Validate a scope file")
    s.add_argument("scope")
    s.set_defaults(func=cmd_scope_check)

    pr = sub.add_parser("prompt", help="Render the prompt Pi will receive")
    pr.add_argument("task")
    pr.set_defaults(func=cmd_prompt)

    pl = sub.add_parser("plan", help="Ask OpenRouter for a safe non-destructive task plan")
    pl.add_argument("task")
    pl.add_argument("--model")
    pl.set_defaults(func=cmd_plan)

    l = sub.add_parser("launch", help="Start a task in tmux, optionally inside Docker/Exegol")
    l.add_argument("task")
    l.add_argument("--config", default=os.environ.get("BB_AGENTS", "configs/agents.example.yaml"))
    l.add_argument("--no-docker", action="store_true", help="Launch a manual shell window instead of Docker")
    l.set_defaults(func=cmd_launch)

    st = sub.add_parser("status", help="Show tmux windows")
    st.add_argument("session")
    st.set_defaults(func=cmd_status)

    ta = sub.add_parser("tail", help="Capture the last lines from a tmux window")
    ta.add_argument("session")
    ta.add_argument("window")
    ta.add_argument("--lines", type=int, default=120)
    ta.set_defaults(func=cmd_tail)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
