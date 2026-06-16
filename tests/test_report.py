from pathlib import Path

from bbagent.logging import RunLog
from bbagent.report import render_report_draft, write_report_draft

ROOT = Path(__file__).resolve().parents[1]


def _load_task_event(run: RunLog) -> None:
    run.write(
        "task_loaded",
        "Loaded task",
        {
            "task": str(ROOT / "tasks" / "example.local.yaml"),
            "scope": str(ROOT / "configs" / "scope.example.yaml"),
        },
    )


def test_render_report_draft_includes_scope_and_timeline(tmp_path):
    run = RunLog(tmp_path)
    _load_task_event(run)
    run.write("tmux_window_started", "Started window")

    text = render_report_draft(run.dir)

    assert "local-toy-header-review" in text
    assert "toy-web" in text
    assert "task_loaded" in text
    assert "## Evidence" in text
    assert "## Scope / authorization" in text


def test_render_report_draft_handles_missing_task_loaded(tmp_path):
    run = RunLog(tmp_path)
    text = render_report_draft(run.dir)
    assert "could not be resolved" in text


def test_write_report_draft_writes_file(tmp_path):
    run = RunLog(tmp_path)
    _load_task_event(run)
    path = write_report_draft(run.dir)
    assert path.name == "report.md"
    assert path.read_text() == render_report_draft(run.dir)
