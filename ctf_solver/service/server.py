"""Background service entry-point coordinating the orchestrator."""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import socket
import threading
import time
from contextlib import closing
from typing import Dict, Optional

from ctf_solver.core.orchestrator import SimpleOrchestrator
from ctf_solver.database.db import get_db_connection

from .constants import DEFAULT_SOCKET_PATH

logger = logging.getLogger(__name__)


class Service:
    """Long-lived background service that owns the orchestrator and IPC."""

    def __init__(
        self,
        socket_path=DEFAULT_SOCKET_PATH,
        max_parallel: int = 1,
        optimized_agent: Optional[str] = None,
    ) -> None:
        self.socket_path = os.fspath(socket_path)
        self.max_parallel = max_parallel
        self.optimized_agent = optimized_agent
        self._server_socket: Optional[socket.socket] = None
        self._shutdown_event = threading.Event()
        self._attempt_status: Dict[int, Dict[str, str]] = {}

        def db_factory():
            return get_db_connection()

        self.orchestrator = SimpleOrchestrator(
            db_factory,
            max_parallel=max_parallel,
            optimized_agent_name=optimized_agent,
            install_signal_handlers=False,
        )

    def start(self) -> None:
        self._setup_socket()
        logger.info("Flaggy service listening on %s", self.socket_path)

        signal.signal(signal.SIGTERM, lambda *_: self.stop())
        signal.signal(signal.SIGINT, lambda *_: self.stop())

        try:
            while not self._shutdown_event.is_set():
                try:
                    client_sock, _ = self._server_socket.accept()
                except OSError as exc:  # noqa: BLE001
                    if self._shutdown_event.is_set():
                        break
                    logger.error("Accept failed: %s", exc)
                    continue
                threading.Thread(target=self._handle_client, args=(client_sock,), daemon=True).start()
        finally:
            self.stop()

    def stop(self) -> None:
        if self._shutdown_event.is_set():
            return
        self._shutdown_event.set()
        logger.info("Stopping flaggy service")
        try:
            if self._server_socket:
                self._server_socket.close()
        except Exception:  # noqa: BLE001
            pass
        self.orchestrator.shutdown()
        try:
            os.remove(self.socket_path)
        except FileNotFoundError:
            pass
        except OSError as exc:  # noqa: BLE001
            logger.warning("Failed to remove socket: %s", exc)

    def _setup_socket(self) -> None:
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self.socket_path)
        os.chmod(self.socket_path, 0o600)
        sock.listen()
        self._server_socket = sock

    def _handle_client(self, client_sock: socket.socket) -> None:
        with closing(client_sock) as sock:
            try:
                header = sock.recv(4)
                if len(header) != 4:
                    raise ValueError("incomplete header")
                length = int.from_bytes(header, "big")
                body = b""
                while len(body) < length:
                    chunk = sock.recv(length - len(body))
                    if not chunk:
                        raise ValueError("socket closed prematurely")
                    body += chunk
                request = json.loads(body.decode("utf-8"))
                action = request.get("action")
                payload = request.get("payload", {})

                if action == "health":
                    response = {"status": "ok", "payload": {"status": "healthy"}}
                elif action == "start_attempt":
                    response = self._handle_start_attempt(payload)
                elif action == "cancel_attempt":
                    response = self._handle_cancel_attempt(payload)
                elif action == "get_attempt_status":
                    response = self._handle_get_attempt_status(payload)
                elif action == "shutdown":
                    response = {"status": "ok", "payload": {"message": "shutting down"}}
                    threading.Thread(target=self.stop, daemon=True).start()
                else:
                    response = {"status": "error", "message": f"unknown action: {action}"}

            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to handle client: %s", exc)
                response = {"status": "error", "message": str(exc)}

            data = json.dumps(response).encode("utf-8")
            sock.sendall(len(data).to_bytes(4, "big"))
            sock.sendall(data)

    def _handle_start_attempt(self, payload: Dict[str, str]) -> Dict[str, object]:
        challenge_id = int(payload["challenge_id"])
        optimized = payload.get("optimized_agent")
        attempt_id_holder: Dict[str, int] = {}

        def _on_attempt_created(attempt_id: int) -> None:
            attempt_id_holder["attempt_id"] = attempt_id
            self._attempt_status[attempt_id] = {"status": "running"}

        def _on_attempt_finished(attempt_id: int, status: str) -> None:
            self._attempt_status[attempt_id] = {"status": status}

        self.orchestrator.submit_challenge(
            challenge_id,
            on_attempt_created=_on_attempt_created,
            on_attempt_finished=_on_attempt_finished,
            optimized_agent_name=optimized,
            use_presenter=False,
        )

        start = time.time()
        while "attempt_id" not in attempt_id_holder and not self._shutdown_event.is_set():
            if time.time() - start > 10:
                raise RuntimeError("Attempt creation timed out")
            time.sleep(0.05)

        attempt_id = attempt_id_holder.get("attempt_id")
        if attempt_id is None:
            raise RuntimeError("Attempt creation failed")

        return {"status": "ok", "payload": {"attempt_id": attempt_id}}

    def _handle_cancel_attempt(self, payload: Dict[str, str]) -> Dict[str, object]:
        attempt_id = int(payload["attempt_id"])
        cancelled = self.orchestrator.request_cancel(attempt_id)
        return {"status": "ok", "payload": {"cancelled": cancelled}}

    def _handle_get_attempt_status(self, payload: Dict[str, str]) -> Dict[str, object]:
        attempt_id = int(payload["attempt_id"])
        status = self._attempt_status.get(attempt_id, {"status": "unknown"})
        return {"status": "ok", "payload": status}


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Flaggy background service")
    parser.add_argument("--socket", default=str(DEFAULT_SOCKET_PATH), help="Unix socket path")
    parser.add_argument("--parallel", type=int, default=1, help="Maximum parallel runs")
    parser.add_argument("--optimized", default=None, help="Default optimized agent name")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))
    service = Service(socket_path=args.socket, max_parallel=args.parallel, optimized_agent=args.optimized)
    service.start()


if __name__ == "__main__":
    main()

