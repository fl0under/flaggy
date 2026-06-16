from pathlib import Path
import py_compile
import stat

from bbagent.harbor_export import export_task_to_harbor


def test_export_local_task_to_harbor(tmp_path: Path):
    out = tmp_path / "harbor"
    task_dir = export_task_to_harbor("tasks/example.local.yaml", out)

    assert (task_dir / "instruction.md").exists()
    assert (task_dir / "task.toml").exists()
    assert (task_dir / "INTERACTIVE.md").exists()
    assert (task_dir / "environment" / "Dockerfile").exists()
    assert (task_dir / "environment" / "workdir" / "app.py").exists()
    assert (task_dir / "tests" / "test.sh").exists()
    assert (task_dir / "tests" / "grade_report.py").exists()
    assert (task_dir / "solution" / "solve.sh").exists()

    instruction = (task_dir / "instruction.md").read_text()
    assert "/logs/artifacts/report.md" in instruction
    assert "http://127.0.0.1:8080" in instruction

    task_toml = (task_dir / "task.toml").read_text()
    assert 'name = "local-toy-header-review"' in task_toml
    assert 'network_mode = "no-network"' in task_toml

    py_compile.compile(str(task_dir / "tests" / "grade_report.py"), doraise=True)
    assert (task_dir / "tests" / "test.sh").stat().st_mode & stat.S_IXUSR
    assert (task_dir / "solution" / "solve.sh").stat().st_mode & stat.S_IXUSR
