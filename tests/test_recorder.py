from bbagent.logging import RunLog
from bbagent.recorder import record_session


def test_record_session_appends_only_new_lines(tmp_path):
    run = RunLog(tmp_path)
    captures = [
        "line1\nline2\n",
        "line1\nline2\nline3\n",
        "line1\nline2\nline3\n",  # unchanged: should not duplicate
    ]
    calls = {"n": 0}

    def capture() -> str:
        text = captures[min(calls["n"], len(captures) - 1)]
        calls["n"] += 1
        return text

    def is_alive() -> bool:
        return calls["n"] < len(captures)

    record_session(run, capture, is_alive=is_alive, interval=0, sleep=lambda s: None)

    transcript = (run.dir / "transcript.log").read_text()
    assert "line1" in transcript
    assert "line2" in transcript
    assert transcript.count("line3") == 1

    types = [e["type"] for e in run.events()]
    assert types[0] == "recording_started"
    assert types[-1] == "recording_stopped"


def test_record_session_falls_back_to_full_capture_on_scroll_loss():
    run_calls: list[str] = []

    class FakeRun:
        def write(self, type_, message, data=None):
            run_calls.append(type_)

        def append_text(self, name, text):
            run_calls.append(text)

    captures = ["a\nb\nc\n", "x\ny\nz\n"]
    idx = {"n": 0}

    def capture() -> str:
        v = captures[idx["n"]]
        idx["n"] += 1
        return v

    def is_alive() -> bool:
        return idx["n"] < len(captures)

    record_session(FakeRun(), capture, is_alive=is_alive, interval=0, sleep=lambda s: None)

    appended = "".join(c for c in run_calls if "\n" in c)
    assert "x" in appended and "y" in appended and "z" in appended
