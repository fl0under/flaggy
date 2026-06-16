from __future__ import annotations

import time
from typing import Callable

from .logging import RunLog

TRANSCRIPT_NAME = "transcript.log"


def _new_lines(previous: list[str], current: list[str]) -> list[str]:
    """Return the suffix of `current` not already captured.

    tmux capture-pane returns a fixed scrollback window, so plain appending
    would duplicate every previously seen line. Find the longest overlap
    between the tail of `previous` and the head of `current` and only return
    what comes after it; if the pane scrolled past the window entirely (no
    overlap), fall back to the full capture rather than silently dropping it.
    """
    if not previous:
        return current
    max_overlap = min(len(previous), len(current))
    for overlap in range(max_overlap, 0, -1):
        if previous[-overlap:] == current[:overlap]:
            return current[overlap:]
    return current


def record_session(
    run: RunLog,
    list_targets: Callable[[], list[str]],
    capture: Callable[[str], str],
    *,
    session_alive: Callable[[], bool],
    interval: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Poll every pane in a tmux session and append newly seen output to transcript.log.

    Targets are (re)discovered on every poll via `list_targets()`, so a pane the
    agent opens mid-task (e.g. a split-window gdb session) is picked up
    automatically without restarting the recorder. Each line is tagged with the
    target it came from. Runs until `session_alive()` reports the session is
    gone, so it's meant to be started as a detached background process for the
    lifetime of a launched task (see orchestrator.start_recorder).
    """
    previous: dict[str, list[str]] = {}
    run.write("recording_started", "Session recorder attached")
    while session_alive():
        try:
            targets = list_targets()
        except Exception as exc:
            run.write("recording_error", str(exc))
            break
        for target in targets:
            if target not in previous:
                previous[target] = []
                run.write("target_discovered", f"New pane discovered: {target}", {"target": target})
            try:
                content = capture(target)
            except Exception as exc:  # tmux can vanish between list_targets() and capture()
                run.write("recording_error", f"{target}: {exc}")
                continue
            current = content.splitlines()
            new = _new_lines(previous[target], current)
            if new:
                stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                chunk = "".join(f"[{stamp}][{target}] {line}\n" for line in new)
                run.append_text(TRANSCRIPT_NAME, chunk)
                run.write("pane_update", f"{len(new)} new line(s) captured", {"target": target})
            previous[target] = current
        sleep(interval)
    run.write("recording_stopped", "tmux session no longer present")
