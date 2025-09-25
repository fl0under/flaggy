"""High-level helper to ensure the flaggy service is running."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .client import ServiceClient
from .constants import DEFAULT_SOCKET_PATH
from .utils import default_service_command, resolve_socket_path


class ServiceSupervisor:
    """Convenience wrapper used by CLI/TUI to interact with the service."""

    def __init__(self, socket_path: Optional[Path] = None, service_cmd: Optional[list[str]] = None) -> None:
        self.socket_path = socket_path or resolve_socket_path()
        self.service_cmd = service_cmd or default_service_command()
        self.client = ServiceClient(socket_path=self.socket_path, service_cmd=self.service_cmd)

    def ensure_running(self) -> None:
        self.client.ensure_running()

    def start_attempt(self, challenge_id: int, optimized_agent: Optional[str] = None) -> int:
        self.ensure_running()
        return self.client.start_attempt(challenge_id, optimized_agent=optimized_agent)

    def cancel_attempt(self, attempt_id: int) -> bool:
        self.ensure_running()
        return self.client.cancel_attempt(attempt_id)

    def get_attempt_status(self, attempt_id: int):
        self.ensure_running()
        return self.client.get_attempt_status(attempt_id)

    def wait_attempt(self, attempt_id: int, poll_interval: float = 1.0):
        self.ensure_running()
        return self.client.wait_attempt(attempt_id, poll_interval=poll_interval)


