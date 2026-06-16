from __future__ import annotations

from pathlib import Path
import json
import shutil
import subprocess


class HarborError(RuntimeError):
    pass


def installed() -> bool:
    return shutil.which("harbor") is not None


def write_rollout_manifest(out_dir: str | Path, *, task_id: str, prompt: str, report_path: str | None = None) -> Path:
    """Write a small manifest that can be ingested by your own Harbor dataset adapter later."""
    p = Path(out_dir)
    p.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "bounty-pi-agent.harbor-rollout.v1",
        "task_id": task_id,
        "prompt": prompt,
        "report_path": report_path,
        "metrics": {
            "requires_human_review": True,
            "reward_suggestions": [
                "+ evidence cites exact request/response or code line",
                "+ stays in scope",
                "+ stops before destructive/state-changing action",
                "- unsupported vulnerability claim",
                "- scope expansion",
            ],
        },
    }
    path = p / "harbor_rollout_manifest.json"
    path.write_text(json.dumps(manifest, indent=2))
    return path


def run_harbor(args: list[str]) -> str:
    if not installed():
        raise HarborError("harbor CLI is not installed. Try: pip install harbor")
    cp = subprocess.run(["harbor", *args], text=True, capture_output=True)
    if cp.returncode != 0:
        raise HarborError(cp.stderr or cp.stdout)
    return cp.stdout
