from pathlib import Path

from bbagent.grader import find_out_of_scope_urls, grade_run
from bbagent.logging import RunLog
from bbagent.scope import Scope

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


def test_find_out_of_scope_urls():
    scope = Scope.load(ROOT / "configs" / "scope.example.yaml")
    text = "curl http://127.0.0.1:8080/health and curl https://example.com/evil"
    bad = find_out_of_scope_urls(text, scope)
    assert bad == ["https://example.com/evil"]


def test_grade_run_flags_missing_report_and_evidence(tmp_path):
    run = RunLog(tmp_path)
    _load_task_event(run)

    result = grade_run(run.dir)

    assert result.checks["task_loaded"] is True
    assert result.checks["report_present"] is False
    assert result.checks["evidence_present"] is False
    assert 0.0 <= result.score <= 1.0


def test_grade_run_detects_out_of_scope_url_in_transcript(tmp_path):
    run = RunLog(tmp_path)
    _load_task_event(run)
    (run.dir / "transcript.log").write_text("[t] curl https://example.com/evil\n")

    result = grade_run(run.dir)

    assert result.checks["no_out_of_scope_urls_in_transcript"] is False
    assert any("example.com/evil" in n for n in result.notes)


def test_grade_run_without_task_loaded_event(tmp_path):
    run = RunLog(tmp_path)
    result = grade_run(run.dir)
    assert result.checks["task_loaded"] is False
    assert result.checks["no_out_of_scope_urls_in_transcript"] is False


def test_find_out_of_scope_urls_strips_trailing_punctuation():
    # Regression: the agent brief renders "http://127.0.0.1:8080, max 30/min",
    # which a naive regex match turns into an invalid port "8080," for urlparse.
    scope = Scope.load(ROOT / "configs" / "scope.example.yaml")
    text = "Allowed targets:\n  * toy-web: http://127.0.0.1:8080, max 30/min — notes"
    assert find_out_of_scope_urls(text, scope) == []
