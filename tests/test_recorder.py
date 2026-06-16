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

    def list_targets() -> list[str]:
        return ["main.0"]

    def capture(target: str) -> str:
        text = captures[min(calls["n"], len(captures) - 1)]
        calls["n"] += 1
        return text

    def session_alive() -> bool:
        return calls["n"] < len(captures)

    record_session(
        run, list_targets, capture, session_alive=session_alive, interval=0, sleep=lambda s: None
    )

    transcript = (run.dir / "transcript.log").read_text()
    assert "line1" in transcript
    assert "line2" in transcript
    assert transcript.count("line3") == 1
    assert "[main.0]" in transcript

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

    def list_targets() -> list[str]:
        return ["main.0"]

    def capture(target: str) -> str:
        v = captures[idx["n"]]
        idx["n"] += 1
        return v

    def session_alive() -> bool:
        return idx["n"] < len(captures)

    record_session(
        FakeRun(), list_targets, capture, session_alive=session_alive, interval=0, sleep=lambda s: None
    )

    appended = "".join(c for c in run_calls if "\n" in c)
    assert "x" in appended and "y" in appended and "z" in appended


def test_record_session_discovers_new_pane_mid_run(tmp_path):
    run = RunLog(tmp_path)
    polls = {"n": 0}
    # First two polls only "main.0" exists; a "gdb.0" pane appears on poll 3.
    targets_by_poll = [["main.0"], ["main.0"], ["main.0", "gdb.0"]]
    main_captures = ["start\n", "start\nmore\n", "start\nmore\n"]
    gdb_captures = ["(gdb) break main\n"]

    def list_targets() -> list[str]:
        return targets_by_poll[min(polls["n"], len(targets_by_poll) - 1)]

    def capture(target: str) -> str:
        if target == "main.0":
            return main_captures[min(polls["n"], len(main_captures) - 1)]
        return gdb_captures[0]

    def session_alive() -> bool:
        return polls["n"] < len(targets_by_poll)

    def advance(s: float) -> None:
        polls["n"] += 1

    record_session(
        run, list_targets, capture, session_alive=session_alive, interval=0, sleep=advance
    )

    transcript = (run.dir / "transcript.log").read_text()
    assert "[main.0]" in transcript
    assert "[gdb.0]" in transcript
    assert "(gdb) break main" in transcript

    discovered = [e for e in run.events() if e["type"] == "target_discovered"]
    assert {e["data"]["target"] for e in discovered} == {"main.0", "gdb.0"}
