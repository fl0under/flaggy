from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Job:
    id: str
    challenge: str
    status: str
    steps: int
    started_at: datetime
    last_action: str
    last_output: str
    flag: str


@dataclass
class LogEntry:
    step: int
    action: str
    output: str
    duration_ms: Optional[int]
    analysis: Optional[str]
    approach: Optional[str]


