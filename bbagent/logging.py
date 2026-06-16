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


def read_events(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    events = []
    with p.open() as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


class RunLog:
    def __init__(self, base_dir: str | Path = "runs", run_id: str | None = None):
        self.run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
        self.dir = Path(base_dir) / self.run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.dir / "events.jsonl"

    @classmethod
    def attach(cls, run_dir: str | Path) -> "RunLog":
        """Reopen an existing run directory (used by the background recorder/report/grade)."""
        d = Path(run_dir)
        if not d.exists():
            raise FileNotFoundError(f"Run directory not found: {d}")
        log = cls.__new__(cls)
        log.run_id = d.name
        log.dir = d
        log.events_path = d / "events.jsonl"
        return log

    def write(self, type_: str, message: str, data: dict | None = None) -> None:
        with self.events_path.open("a") as f:
            f.write(Event(type_, message, data).as_json() + "\n")

    def write_markdown(self, name: str, text: str) -> Path:
        path = self.dir / name
        path.write_text(text)
        return path

    def append_text(self, name: str, text: str) -> Path:
        path = self.dir / name
        with path.open("a") as f:
            f.write(text)
        return path

    def events(self) -> list[dict]:
        return read_events(self.events_path)
