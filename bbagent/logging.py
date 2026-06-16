from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import uuid


@dataclass
class Event:
    type: str
    message: str
    data: dict | None = None
    ts: str = ""

    def as_json(self) -> str:
        payload = asdict(self)
        payload["ts"] = payload["ts"] or datetime.now(timezone.utc).isoformat()
        return json.dumps(payload, sort_keys=True)


class RunLog:
    def __init__(self, base_dir: str | Path = "runs", run_id: str | None = None):
        self.run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
        self.dir = Path(base_dir) / self.run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.dir / "events.jsonl"

    def write(self, type_: str, message: str, data: dict | None = None) -> None:
        with self.events_path.open("a") as f:
            f.write(Event(type_, message, data).as_json() + "\n")

    def write_markdown(self, name: str, text: str) -> Path:
        path = self.dir / name
        path.write_text(text)
        return path
