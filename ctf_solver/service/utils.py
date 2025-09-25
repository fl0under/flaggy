"""Utility helpers for the flaggy service layer."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .constants import DEFAULT_SOCKET_PATH


def default_service_command() -> list[str]:
    """Return the default command used to launch the background service."""

    python_exec = os.environ.get("FLAGGY_PYTHON", sys.executable)
    return [python_exec, "-m", "ctf_solver.service.server", "--socket", str(DEFAULT_SOCKET_PATH)]


def resolve_socket_path() -> Path:
    """Resolve the service socket path, ensuring the parent directory exists."""

    socket_path = DEFAULT_SOCKET_PATH
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    return socket_path


