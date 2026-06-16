from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import yaml


class TaskError(ValueError):
    pass


@dataclass(frozen=True)
class Task:
    id: str
    kind: str
    scope: str
    agent: str
    target: str
    objective: str
    constraints: list[str]
    expected_outputs: list[str]

    @classmethod
    def load(cls, path: str | Path) -> "Task":
        p = Path(path).expanduser().resolve()
        raw = yaml.safe_load(p.read_text()) or {}
        try:
            return cls(
                id=raw["id"],
                kind=raw.get("kind", "manual"),
                scope=raw["scope"],
                agent=raw.get("agent", "scout"),
                target=raw["target"],
                objective=raw["objective"].strip(),
                constraints=list(raw.get("constraints", [])),
                expected_outputs=list(raw.get("expected_outputs", [])),
            )
        except KeyError as exc:
            raise TaskError(f"Missing required task field: {exc}") from exc

    def render(self) -> str:
        lines = [f"Task ID: {self.id}", f"Kind: {self.kind}", f"Agent: {self.agent}", f"Target: {self.target}", "", "Objective:", self.objective, ""]
        if self.constraints:
            lines.append("Constraints:")
            lines.extend(f"- {item}" for item in self.constraints)
            lines.append("")
        if self.expected_outputs:
            lines.append("Expected outputs:")
            lines.extend(f"- {item}" for item in self.expected_outputs)
        return "\n".join(lines)
