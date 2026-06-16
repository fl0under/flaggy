from __future__ import annotations

from pathlib import Path

from .logging import read_events
from .scope import Scope
from .tasks import Task

REPORT_NAME = "report.md"
TRANSCRIPT_NAME = "transcript.log"
DEFAULT_TRANSCRIPT_TAIL_LINES = 40


def resolve_task_and_scope(run_dir: Path) -> tuple[Task | None, Scope | None]:
    """Recover the task/scope a run was launched with from its task_loaded event."""
    events = read_events(run_dir / "events.jsonl")
    loaded = next((e for e in events if e.get("type") == "task_loaded"), None)
    if not loaded:
        return None, None
    data = loaded.get("data") or {}
    task = Task.load(data["task"]) if data.get("task") else None
    scope = Scope.load(data["scope"]) if data.get("scope") else None
    return task, scope


def evidence_files(scope: Scope | None) -> list[Path]:
    if scope is None:
        return []
    evidence_dir = Path(scope.evidence_dir)
    if not evidence_dir.exists():
        return []
    return sorted(p for p in evidence_dir.rglob("*") if p.is_file())


def transcript_tail(run_dir: Path, lines: int = DEFAULT_TRANSCRIPT_TAIL_LINES) -> str:
    transcript = run_dir / TRANSCRIPT_NAME
    if not transcript.exists():
        return ""
    content = transcript.read_text().splitlines()
    return "\n".join(content[-lines:])


def render_report_draft(run_dir: Path) -> str:
    """Assemble a report.md skeleton from a run's events, evidence, and transcript.

    Facts (timeline, scope, evidence file list) are filled in automatically;
    analysis (impact, repro, remediation) is intentionally left as TODO so the
    agent or a human states it explicitly rather than this tool guessing.
    """
    run_dir = Path(run_dir)
    task, scope = resolve_task_and_scope(run_dir)
    events = read_events(run_dir / "events.jsonl")
    evidence = evidence_files(scope)
    tail = transcript_tail(run_dir)

    title = task.id if task else run_dir.name
    lines = [f"# {title}", ""]

    lines += ["## Summary", "", "TODO: one or two sentence summary of the finding(s), if any.", ""]

    lines += ["## Scope / authorization", ""]
    if scope and task:
        target = scope.target(task.target)
        lines += [
            f"- Program: {scope.program} ({scope.mode})",
            f"- Target: ({target.kind}) {target.name} — {target.locator()}",
            f"- Policy: {scope.policy_url or 'not provided'}",
        ]
    else:
        lines.append("- Scope/task could not be resolved from this run's events.jsonl.")
    lines.append("")

    lines += ["## Impact", "", "TODO: concrete security impact, or state 'no issue found'.", ""]
    lines += ["## Reproduction steps", "", "TODO: minimal, safe, non-destructive steps.", ""]

    lines += ["## Evidence", "", "Timeline:"]
    if events:
        for e in events:
            lines.append(f"- `{e.get('ts', '')}` **{e.get('type', '')}** {e.get('message', '')}")
    else:
        lines.append("- (no events recorded)")
    lines += ["", "Evidence files:"]
    if evidence:
        for f in evidence:
            lines.append(f"- `{f}`")
    else:
        lines.append("- (none found in the scope's evidence_dir)")
    if tail:
        lines += ["", "Transcript tail:", "```", tail, "```"]
    lines.append("")

    lines += ["## Suggested remediation", "", "TODO", ""]
    lines += [
        "## Notes / uncertainty",
        "",
        "TODO: call out anything unverified, low-confidence, or out of scope.",
        "",
    ]

    return "\n".join(lines)


def write_report_draft(run_dir: Path) -> Path:
    text = render_report_draft(run_dir)
    path = Path(run_dir) / REPORT_NAME
    path.write_text(text)
    return path
