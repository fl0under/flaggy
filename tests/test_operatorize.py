from pathlib import Path

import pytest

from bbagent.operatorize import (
    OperatorizeError,
    find_task_dirs,
    operatorize_tree,
    retarget_dockerfile,
)

IMAGE = "flaggy-operator:latest"


def _make_task(root: Path, name: str, dockerfile: str, *, config: str = "task.toml") -> Path:
    task = root / name
    (task / "environment").mkdir(parents=True)
    (task / "environment" / "Dockerfile").write_text(dockerfile)
    (task / config).write_text("name = 'x'\n")
    return task


def test_retarget_single_stage(tmp_path: Path):
    task = _make_task(tmp_path, "t1", "FROM kalilinux/kali-rolling\nRUN echo hi\nCOPY flag.txt /flag\n")
    res = retarget_dockerfile(task / "environment" / "Dockerfile", IMAGE)
    assert res.changed
    assert res.original_base == "kalilinux/kali-rolling"
    text = (task / "environment" / "Dockerfile").read_text()
    assert f"FROM {IMAGE}" in text
    # Challenge build steps are preserved; original base recorded as a comment.
    assert "RUN echo hi" in text
    assert "COPY flag.txt /flag" in text
    assert "# flaggy operatorize: base was kalilinux/kali-rolling" in text


def test_retarget_is_idempotent(tmp_path: Path):
    df = tmp_path / "t" / "environment" / "Dockerfile"
    _make_task(tmp_path, "t", "FROM debian:bookworm\n")
    first = retarget_dockerfile(df, IMAGE)
    assert first.changed
    second = retarget_dockerfile(df, IMAGE)
    assert not second.changed
    # No stacked comments or duplicate FROM lines.
    assert df.read_text().count("FROM ") == 1
    assert df.read_text().count("# flaggy operatorize") == 1


def test_multistage_retargets_final_and_keeps_builder(tmp_path: Path):
    dockerfile = "FROM golang:1.22 AS build\nRUN go build\nFROM debian:bookworm\nCOPY --from=build /app /app\n"
    task = _make_task(tmp_path, "multi", dockerfile)
    res = retarget_dockerfile(task / "environment" / "Dockerfile", IMAGE)
    assert res.changed and res.multi_from
    text = (task / "environment" / "Dockerfile").read_text()
    assert "FROM golang:1.22 AS build" in text  # builder stage untouched
    assert f"FROM {IMAGE}" in text
    assert "COPY --from=build /app /app" in text


def test_refuses_to_rewrite_stage_alias(tmp_path: Path):
    dockerfile = "FROM debian AS base\nRUN apt-get update\nFROM base\nCOPY x /x\n"
    task = _make_task(tmp_path, "alias", dockerfile)
    res = retarget_dockerfile(task / "environment" / "Dockerfile", IMAGE)
    assert not res.changed
    assert "build stage" in (res.skipped_reason or "")


def test_dry_run_does_not_write(tmp_path: Path):
    task = _make_task(tmp_path, "t", "FROM debian\n")
    df = task / "environment" / "Dockerfile"
    res = retarget_dockerfile(df, IMAGE, dry_run=True)
    assert res.changed
    assert "FROM debian" in df.read_text()
    assert IMAGE not in df.read_text()


def test_find_task_dirs_and_tree(tmp_path: Path):
    _make_task(tmp_path / "dataset", "benchmark-a", "FROM debian\n")
    _make_task(tmp_path / "dataset", "benchmark-b", "FROM ubuntu\n", config="task.yaml")
    (tmp_path / "dataset" / "not-a-task").mkdir()
    dirs = find_task_dirs(tmp_path / "dataset")
    assert len(dirs) == 2
    results = operatorize_tree(tmp_path / "dataset", IMAGE)
    assert sum(r.changed for r in results) == 2


def test_errors_when_no_tasks(tmp_path: Path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(OperatorizeError):
        operatorize_tree(tmp_path / "empty", IMAGE)
