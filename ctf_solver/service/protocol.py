"""Protocol definitions for the flaggy service IPC."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class Request:
    action: str
    payload: Dict[str, Any]

    def to_json(self) -> bytes:
        return json.dumps({"action": self.action, "payload": self.payload}).encode("utf-8")


@dataclass
class Response:
    status: str
    payload: Dict[str, Any]

    @classmethod
    def from_bytes(cls, data: bytes) -> "Response":
        raw = json.loads(data.decode("utf-8"))
        return cls(status=raw.get("status", "error"), payload=raw.get("payload", {}))

    def raise_for_status(self) -> None:
        if self.status != "ok":
            message = self.payload.get("message", "unknown error")
            raise RuntimeError(message)


