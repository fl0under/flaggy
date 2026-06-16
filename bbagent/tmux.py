from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


class TmuxError(RuntimeError):
    pass


def _run(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    if not shutil.which("tmux"):
        raise TmuxError("tmux is not installed or not on PATH")
    return subprocess.run(["tmux", *args], text=True, capture_output=True, check=check)


@dataclass
class TmuxSession:
    name: str

    def exists(self) -> bool:
        return _run(["has-session", "-t", self.name], check=False).returncode == 0

    def ensure(self) -> None:
        if not self.exists():
            _run(["new-session", "-d", "-s", self.name, "-n", "control"])

    def new_window(self, name: str, command: str) -> None:
        self.ensure()
        _run(["new-window", "-t", self.name, "-n", name, command])

    def send_keys(self, target: str, keys: str) -> None:
        _run(["send-keys", "-t", target, keys, "C-m"])

    def list_windows(self) -> list[dict[str, str]]:
        self.ensure()
        fmt = "#{window_index}\t#{window_name}\t#{pane_current_command}\t#{pane_pid}"
        out = _run(["list-windows", "-t", self.name, "-F", fmt]).stdout
        windows = []
        for line in out.splitlines():
            idx, name, command, pid = (line.split("\t") + ["", "", "", ""])[:4]
            windows.append({"index": idx, "name": name, "command": command, "pid": pid})
        return windows

    def capture(self, window: str | int, lines: int = 120) -> str:
        target = f"{self.name}:{window}"
        return _run(["capture-pane", "-p", "-t", target, "-S", f"-{lines}"]).stdout
