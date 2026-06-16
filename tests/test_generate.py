import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bbagent.generate import (
    ENCODERS,
    GenerateError,
    generate_challenge,
    generate_dataset,
)


def test_generate_dataset_layout(tmp_path: Path):
    paths = generate_dataset(tmp_path, count=8, seed=0)
    assert len(paths) == 8
    for task in paths:
        assert (task / "instruction.md").exists()
        assert (task / "task.toml").exists()
        assert (task / "environment" / "Dockerfile").exists()
        assert (task / "tests" / "grade_flag.py").exists()
        assert (task / "tests" / "test.sh").exists()
        assert (task / "solution" / "solve.sh").exists()
        # exactly one challenge file is shipped to the agent
        assert list((task / "environment" / "workdir").iterdir())


def test_deterministic_by_seed():
    a = generate_challenge(42, "xor-single")
    b = generate_challenge(42, "xor-single")
    c = generate_challenge(43, "xor-single")
    assert a.flag == b.flag and a.files == b.files
    assert a.flag != c.flag


def test_flag_not_leaked_to_agent(tmp_path: Path):
    # The plaintext flag must never appear in anything the agent can read.
    [task] = generate_dataset(tmp_path, count=1, seed=7, categories=["xor-single"])
    ch = generate_challenge(7, "xor-single")
    agent_visible = (task / "instruction.md").read_text()
    for f in (task / "environment" / "workdir").iterdir():
        agent_visible += f.read_text()
    assert ch.flag not in agent_visible
    # ...but the verifier (not given to the agent) does hold it.
    assert ch.flag in (task / "tests" / "grade_flag.py").read_text()


@pytest.mark.parametrize("category", list(ENCODERS))
def test_oracle_solves_every_category(tmp_path: Path, category: str):
    ch = generate_challenge(123, category)
    workdir = tmp_path / "app"
    workdir.mkdir()
    for name, content in ch.files.items():
        (workdir / name).write_text(content)
    # Run the embedded oracle exactly as solve.sh would, against the challenge files.
    proc = subprocess.run(
        [sys.executable, "-c", ch.solve_py],
        env={**os.environ, "CHALLENGE_DIR": str(workdir)},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == ch.flag


def _run_grader(task: Path, artifacts: Path, reward: Path) -> int:
    return subprocess.run(
        [sys.executable, str(task / "tests" / "grade_flag.py")],
        env={**os.environ, "FLAGGY_ARTIFACTS": str(artifacts), "FLAGGY_REWARD": str(reward)},
    ).returncode


def test_grader_rewards_correct_flag_only(tmp_path: Path):
    [task] = generate_dataset(tmp_path / "ds", count=1, seed=1, categories=["caesar"])
    ch = generate_challenge(1, "caesar")
    art = tmp_path / "artifacts"
    art.mkdir()
    reward = tmp_path / "reward.json"

    # Correct flag -> reward 1.0, exit 0.
    (art / "flag.txt").write_text(ch.flag + "\n")
    assert _run_grader(task, art, reward) == 0
    assert json.loads(reward.read_text()) == {"reward": 1.0, "solved": True}

    # Wrong flag -> reward 0.0, exit 1.
    (art / "flag.txt").write_text("flag{nope}\n")
    assert _run_grader(task, art, reward) == 1
    assert json.loads(reward.read_text())["solved"] is False


def test_unknown_category_rejected(tmp_path: Path):
    with pytest.raises(GenerateError):
        generate_dataset(tmp_path, count=1, categories=["nope"])
