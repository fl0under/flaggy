"""Retarget Harbor / Terminal-Bench tasks onto a prebuilt operator image.

Terminus runs *inside* each task's own container, so to give the agent the
Exegol toolbox you swap the base image of every task's `environment/Dockerfile`.
Rewriting only the final `FROM` preserves the rest of the build — including the
`COPY` of challenge files and any target setup — so a CTF task still works, just
with a richer toolbox underneath.

This is deliberately format-agnostic: it only touches `environment/Dockerfile`,
so it works on both `task.toml` (Harbor 2.x) and `task.yaml` (Terminal-Bench 1.x)
adapter output such as `adapters/cybench`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


class OperatorizeError(RuntimeError):
    pass


FROM_RE = re.compile(r"^\s*FROM\s+(\S+)", re.IGNORECASE)
FROM_PARTS_RE = re.compile(r"^(\s*FROM\s+)(\S+)(.*)$", re.IGNORECASE)
STAGE_RE = re.compile(r"^\s*FROM\s+\S+\s+AS\s+(\S+)", re.IGNORECASE)
COMMENT_PREFIX = "# flaggy operatorize: base was "


@dataclass
class RetargetResult:
    path: Path
    changed: bool
    original_base: str = ""
    new_base: str = ""
    multi_from: bool = False
    skipped_reason: str | None = None


def _stage_names(lines: list[str]) -> set[str]:
    names = set()
    for line in lines:
        m = STAGE_RE.match(line)
        if m:
            names.add(m.group(1).lower())
    return names


def retarget_dockerfile(path: Path, image: str, *, dry_run: bool = False) -> RetargetResult:
    """Point the final FROM of a Dockerfile at `image`, preserving everything else."""
    text = path.read_text()
    lines = text.splitlines()
    from_idxs = [i for i, line in enumerate(lines) if FROM_RE.match(line)]
    if not from_idxs:
        return RetargetResult(path, False, skipped_reason="no FROM instruction")

    target = from_idxs[-1]
    multi = len(from_idxs) > 1
    m = FROM_PARTS_RE.match(lines[target])
    assert m is not None  # guaranteed by FROM_RE match above
    prefix, original, tail = m.group(1), m.group(2), m.group(3)

    # Don't rewrite a stage alias like `FROM builder AS final`.
    if original.lower() in _stage_names(lines):
        return RetargetResult(
            path, False, original, image, multi,
            skipped_reason=f"final FROM references build stage '{original}'",
        )
    if original == image:
        return RetargetResult(path, False, original, image, multi)

    lines[target] = f"{prefix}{image}{tail}"
    comment = f"{COMMENT_PREFIX}{original}"
    if target > 0 and lines[target - 1].startswith(COMMENT_PREFIX):
        # Idempotent: keep the very first recorded original base.
        pass
    else:
        lines.insert(target, comment)

    if not dry_run:
        trailing = "\n" if text.endswith("\n") else ""
        path.write_text("\n".join(lines) + trailing)
    return RetargetResult(path, True, original, image, multi)


def is_task_dir(path: Path) -> bool:
    return (path / "environment" / "Dockerfile").is_file() and (
        (path / "task.toml").is_file() or (path / "task.yaml").is_file()
    )


def find_task_dirs(root: Path) -> list[Path]:
    root = root.resolve()
    if is_task_dir(root):
        return [root]
    found = {
        dockerfile.parent.parent
        for dockerfile in root.rglob("environment/Dockerfile")
        if is_task_dir(dockerfile.parent.parent)
    }
    return sorted(found)


def operatorize_tree(root: str | Path, image: str, *, dry_run: bool = False) -> list[RetargetResult]:
    root = Path(root).resolve()
    if not root.exists():
        raise OperatorizeError(f"Path not found: {root}")
    task_dirs = find_task_dirs(root)
    if not task_dirs:
        raise OperatorizeError(
            f"No Harbor/Terminal-Bench tasks under {root} "
            "(expected directories with environment/Dockerfile + task.toml|task.yaml)."
        )
    results = []
    for task_dir in task_dirs:
        results.append(retarget_dockerfile(task_dir / "environment" / "Dockerfile", image, dry_run=dry_run))
    return results
