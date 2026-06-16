from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from rich.console import Console
from rich.table import Table

from .grader import grade_run
from .llm import OpenRouterClient, OpenRouterConfig
from .logging import RunLog
from .orchestrator import launch_task, render_system_prompt
from .recorder import record_session
from .report import write_report_draft
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
        info = launch_task(args.task, args.config, no_docker=args.no_docker, record=not args.no_record)
    except (ScopeError, TmuxError, Exception) as exc:  # broad by design: CLI should print readable failure
        console.print(f"[red]Launch failed:[/red] {exc}")
        return 1
    console.print("[green]Started[/green]")
    for k, v in info.items():
        console.print(f"{k}: {v}")
    console.print(f"Attach with: tmux attach -t {info['session']}")
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    run = RunLog.attach(args.run_dir)
    session = TmuxSession(args.session)
    fixed_targets = args.target or None

    def list_targets() -> list[str]:
        return fixed_targets if fixed_targets else session.pane_targets()

    def capture(target: str) -> str:
        return session.capture(target, lines=args.lines)

    record_session(
        run,
        list_targets,
        capture,
        session_alive=session.exists,
        interval=args.interval,
    )
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    if not run_dir.exists():
        console.print(f"[red]Run dir not found:[/red] {run_dir}")
        return 2
    path = write_report_draft(run_dir)
    console.print(f"[green]Draft report written[/green]: {path}")
    console.print("Fill in the TODO sections (impact, repro, remediation) before sharing.")
    return 0


def cmd_grade(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    if not run_dir.exists():
        console.print(f"[red]Run dir not found:[/red] {run_dir}")
        return 2
    result = grade_run(run_dir)

    table = Table(title=f"Grade: {run_dir.name}")
    table.add_column("check")
    table.add_column("result")
    for name, passed in result.checks.items():
        table.add_row(name, "[green]pass[/green]" if passed else "[red]fail[/red]")
    console.print(table)
    console.print(f"Score: {result.score:.0%}")
    for note in result.notes:
        console.print(f"[yellow]note:[/yellow] {note}")

    if args.write:
        path = run_dir / "grade.json"
        path.write_text(json.dumps(result.to_dict(run_dir.name), indent=2))
        console.print(f"Wrote {path}")
    if args.json:
        console.print(json.dumps(result.to_dict(run_dir.name), indent=2))
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
    l.add_argument(
        "--no-record",
        action="store_true",
        help="Skip starting the background transcript recorder for this run",
    )
    l.set_defaults(func=cmd_launch)

    st = sub.add_parser("status", help="Show tmux windows")
    st.add_argument("session")
    st.set_defaults(func=cmd_status)

    ta = sub.add_parser("tail", help="Capture the last lines from a tmux window")
    ta.add_argument("session")
    ta.add_argument("window")
    ta.add_argument("--lines", type=int, default=120)
    ta.set_defaults(func=cmd_tail)

    rc = sub.add_parser(
        "record",
        help="Tail every pane in a tmux session into <run_dir>/transcript.log until the "
        "session closes, auto-discovering new panes (e.g. a gdb split) as they appear "
        "(started automatically by launch; rarely invoked directly)",
    )
    rc.add_argument("run_dir")
    rc.add_argument("session")
    rc.add_argument(
        "--target",
        action="append",
        help="Pane target ('window' or 'window.pane') to record, instead of auto-discovering "
        "all panes. May be passed multiple times.",
    )
    rc.add_argument("--interval", type=float, default=5.0)
    rc.add_argument("--lines", type=int, default=2000)
    rc.set_defaults(func=cmd_record)

    rp = sub.add_parser("report", help="Draft report.md from a run's events, evidence, and transcript")
    rp.add_argument("run_dir")
    rp.set_defaults(func=cmd_report)

    gr = sub.add_parser("grade", help="Score a run against scope/evidence/report completeness checks")
    gr.add_argument("run_dir")
    gr.add_argument("--write", action="store_true", help="Write grade.json into the run dir")
    gr.add_argument("--json", action="store_true", help="Print the grade as JSON")
    gr.set_defaults(func=cmd_grade)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
