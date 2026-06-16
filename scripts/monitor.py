#!/usr/bin/env python3
from __future__ import annotations

import curses
import subprocess
import sys
import time


def tmux(args: list[str]) -> str:
    return subprocess.run(["tmux", *args], text=True, capture_output=True).stdout


def main(stdscr, session: str) -> None:
    curses.curs_set(0)
    stdscr.nodelay(True)
    selected = 0
    while True:
        h, w = stdscr.getmaxyx()
        stdscr.erase()
        stdscr.addstr(0, 0, f"bounty-pi-agent monitor — session {session} — q quit, ↑/↓ select, enter attach"[: w - 1])
        rows = tmux(["list-windows", "-t", session, "-F", "#{window_index}\t#{window_name}\t#{pane_current_command}\t#{pane_pid}"]).splitlines()
        if not rows:
            stdscr.addstr(2, 0, "No windows or tmux session not found."[: w - 1])
        for i, row in enumerate(rows[: max(1, h // 2 - 2)]):
            prefix = "> " if i == selected else "  "
            try:
                idx, name, cmd, pid = row.split("\t")
            except ValueError:
                idx, name, cmd, pid = "?", row, "", ""
            line = f"{prefix}{idx:>2} {name:<26} {cmd:<16} pid={pid}"
            stdscr.addstr(2 + i, 0, line[: w - 1], curses.A_REVERSE if i == selected else 0)
        if rows:
            idx = rows[selected].split("\t")[0]
            pane = tmux(["capture-pane", "-p", "-t", f"{session}:{idx}", "-S", "-20"])
            y = max(4, h // 2)
            stdscr.addstr(y - 1, 0, "─" * (w - 1))
            for j, line in enumerate(pane.splitlines()[-(h - y - 1) :]):
                stdscr.addstr(y + j, 0, line[: w - 1])
        stdscr.refresh()
        ch = stdscr.getch()
        if ch in {ord("q"), 27}:
            return
        if ch in {curses.KEY_UP, ord("k")} and rows:
            selected = max(0, selected - 1)
        if ch in {curses.KEY_DOWN, ord("j")} and rows:
            selected = min(len(rows) - 1, selected + 1)
        if ch in {10, 13} and rows:
            idx = rows[selected].split("\t")[0]
            subprocess.run(["tmux", "switch-client", "-t", f"{session}:{idx}"])
            return
        time.sleep(0.2)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: monitor.py <tmux-session>", file=sys.stderr)
        sys.exit(2)
    curses.wrapper(main, sys.argv[1])
