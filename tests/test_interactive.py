from pathlib import Path

import pytest

from bbagent.harbor_export import export_task_to_harbor
from bbagent.interactive import interactive_command, resolve_interactive_task


def test_resolve_interactive_task_exports_yaml(tmp_path: Path):
    task_dir = resolve_interactive_task("tasks/example.local.yaml", out_dir=tmp_path)
    assert (task_dir / "task.toml").exists()
    assert (task_dir / "environment" / "Dockerfile").exists()


def test_interactive_command_builds_same_environment(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("bbagent.interactive.shutil.which", lambda name: "/usr/bin/docker")
    task_dir = export_task_to_harbor("tasks/example.local.yaml", tmp_path)
    cmd = interactive_command(task_dir, tool="pi", image_tag="flaggy-test")
    joined = " ".join(cmd)
    assert "docker build -t flaggy-test" in joined
    assert str(task_dir / "environment") in joined
    assert "docker run" in joined
    assert "--network none" in joined
    assert "pi @/app/instruction.md" in joined
    assert "/app/instruction.md:ro" in joined


def test_interactive_command_rejects_unknown_tool(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("bbagent.interactive.shutil.which", lambda name: "/usr/bin/docker")
    task_dir = export_task_to_harbor("tasks/example.local.yaml", tmp_path)
    with pytest.raises(Exception):
        interactive_command(task_dir, tool="unknown")


def test_interactive_command_uses_prebuilt_image(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("bbagent.interactive.shutil.which", lambda name: "/usr/bin/docker")
    task_dir = export_task_to_harbor("tasks/example.local.yaml", tmp_path)
    cmd = interactive_command(task_dir, tool="shell", image="flaggy-operator:latest")
    joined = " ".join(cmd)
    # No per-task build when a prebuilt operator image is supplied.
    assert "docker build" not in joined
    assert "docker run" in joined
    assert "flaggy-operator:latest" in joined
    # Task files are mounted instead of baked in, and the instruction is still mounted.
    assert f"{task_dir / 'environment' / 'workdir'}:/app" in joined
    assert "/app/instruction.md:ro" in joined
    assert "--network none" in joined
