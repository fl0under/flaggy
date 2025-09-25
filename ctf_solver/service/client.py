"""Client for the background flaggy service."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .constants import DEFAULT_SOCKET_PATH, SERVICE_START_TIMEOUT
from .errors import ServiceError, ServiceProtocolError, ServiceTimeout, ServiceUnavailable


@dataclass
class ServiceClient:
    socket_path: Path = DEFAULT_SOCKET_PATH
    service_cmd: Optional[list[str]] = None

    def _connect(self) -> socket.socket:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(str(self.socket_path))
        except OSError as exc:  # noqa: BLE001
            sock.close()
            raise ServiceUnavailable(str(exc))
        return sock

    def _send_request(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        message = {"action": action, "payload": payload}
        data = json.dumps(message).encode("utf-8")
        with closing(self._connect()) as sock:
            sock.sendall(len(data).to_bytes(4, "big"))
            sock.sendall(data)
            header = sock.recv(4)
            if len(header) != 4:
                raise ServiceProtocolError("Incomplete response header")
            length = int.from_bytes(header, "big")
            body = b""
            while len(body) < length:
                chunk = sock.recv(length - len(body))
                if not chunk:
                    raise ServiceProtocolError("Socket closed during response")
                body += chunk
        try:
            response = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:  # noqa: BLE001
            raise ServiceProtocolError(f"Malformed JSON: {exc}")
        status = response.get("status")
        if status != "ok":
            message = response.get("message", "error")
            raise ServiceError(message)
        return response.get("payload", {})

    def ensure_running(self, timeout: float = SERVICE_START_TIMEOUT) -> None:
        try:
            self.health_check()
            return
        except ServiceUnavailable:
            pass

        if not self.service_cmd:
            raise ServiceUnavailable("service not running and no launch command provided")

        env = os.environ.copy()
        env.setdefault("FLAGGY_SERVICE_SOCKET", str(self.socket_path))
        subprocess.Popen(self.service_cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        end_time = time.time() + timeout
        while time.time() < end_time:
            try:
                self.health_check()
                return
            except ServiceUnavailable:
                time.sleep(0.1)
        raise ServiceTimeout("Timed out waiting for service to start")

    def health_check(self) -> Dict[str, Any]:
        return self._send_request("health", {})

    def start_attempt(self, challenge_id: int, optimized_agent: Optional[str] = None) -> int:
        payload = {"challenge_id": challenge_id}
        if optimized_agent:
            payload["optimized_agent"] = optimized_agent
        response = self._send_request("start_attempt", payload)
        return int(response["attempt_id"])

    def cancel_attempt(self, attempt_id: int) -> bool:
        payload = {"attempt_id": attempt_id}
        response = self._send_request("cancel_attempt", payload)
        return bool(response.get("cancelled", False))

    def get_attempt_status(self, attempt_id: int) -> Dict[str, Any]:
        payload = {"attempt_id": attempt_id}
        return self._send_request("get_attempt_status", payload)

    def wait_attempt(self, attempt_id: int, poll_interval: float = 1.0) -> Dict[str, Any]:
        while True:
            status = self.get_attempt_status(attempt_id)
            if status.get("status") not in {"running", "queued"}:
                return status
            time.sleep(poll_interval)


