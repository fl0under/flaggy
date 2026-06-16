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
    capture: Callable[[], str],
    *,
    is_alive: Callable[[], bool],
    interval: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Poll a tmux pane and append newly seen output to transcript.log.

    Runs until `is_alive()` reports the window is gone, so it's meant to be
    started as a detached background process for the lifetime of a launched
    task window (see orchestrator.start_recorder).
    """
    previous: list[str] = []
    run.write("recording_started", "Pane recorder attached")
    while is_alive():
        try:
            content = capture()
        except Exception as exc:  # tmux can vanish between is_alive() and capture()
            run.write("recording_error", str(exc))
            break
        current = content.splitlines()
        new = _new_lines(previous, current)
        if new:
            stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            chunk = "".join(f"[{stamp}] {line}\n" for line in new)
            run.append_text(TRANSCRIPT_NAME, chunk)
            run.write("pane_update", f"{len(new)} new line(s) captured")
        previous = current
        sleep(interval)
    run.write("recording_stopped", "tmux window no longer present")
