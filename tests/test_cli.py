from argparse import Namespace
from pathlib import Path

from bbagent import cli
from bbagent.operatorize import RetargetResult


def test_operatorize_guidance_uses_harbor(monkeypatch, tmp_path: Path, capsys):
    task = tmp_path / "dataset" / "task-one"
    task.mkdir(parents=True)

    monkeypatch.setattr(cli, "operatorize_tree", lambda path, image, dry_run=False: [
        RetargetResult(
            path=task,
            original_base="debian:bookworm",
            new_base=image,
            changed=True,
        )
    ])
    monkeypatch.setattr(cli, "is_task_dir", lambda path: False)

    code = cli.cmd_operatorize(
        Namespace(path=str(tmp_path / "dataset"), image="flaggy-operator:latest", dry_run=False)
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "harbor run -p" in out
    assert "-a oracle" in out
    assert "-a terminus-2" in out
    assert "tb run" not in out


def test_operatorize_single_task_guidance_uses_task_path(monkeypatch, tmp_path: Path, capsys):
    task = tmp_path / "dataset" / "task-one"
    task.mkdir(parents=True)

    monkeypatch.setattr(cli, "operatorize_tree", lambda path, image, dry_run=False: [
        RetargetResult(
            path=task,
            original_base="debian:bookworm",
            new_base=image,
            changed=True,
        )
    ])
    monkeypatch.setattr(cli, "is_task_dir", lambda path: True)

    code = cli.cmd_operatorize(
        Namespace(path=str(task), image="flaggy-operator:latest", dry_run=False)
    )

    out = capsys.readouterr().out
    assert code == 0
    assert f"harbor run -p {task.resolve()}" in out
    assert "--include-task-name" not in out
    assert "tb run" not in out


def test_generate_guidance_uses_harbor(monkeypatch, tmp_path: Path, capsys):
    out_dir = tmp_path / "train"
    monkeypatch.setattr(cli, "generate_dataset", lambda *args, **kwargs: [out_dir / "task-one"])

    code = cli.cmd_generate(
        Namespace(
            out=str(out_dir),
            count=1,
            seed=0,
            categories=None,
            force=False,
        )
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "harbor run -p" in out
    assert "-a oracle" in out
    assert "-a terminus-2" in out
    assert "tb run" not in out
