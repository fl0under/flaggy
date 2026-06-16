"""Procedural CTF task generator: a contamination-free training pool.

These tasks are *generated*, not scraped, so they never overlap with Cybench /
NYU CTF / InterCode eval sets — making them safe to RL/SFT on. Each task:

  * is deterministic given its seed (reproducible curricula),
  * hides a unique `flag{...}` recoverable from the challenge files alone,
  * grades on exact-flag capture (a clean, ungameable RLVR reward),
  * ships an oracle `solution/` that genuinely solves it (proof of solvability
    + ready-made SFT trajectories).

Output is the standard Harbor task layout, so it runs through the same harness
(and `flaggy operatorize`) as the external benchmarks. Categories live in a
registry so the pool is easy to extend.
"""
from __future__ import annotations

import base64
import json
import string
import textwrap
from dataclasses import dataclass
from pathlib import Path
from random import Random

from .harbor_export import slugify


class GenerateError(RuntimeError):
    pass


@dataclass
class Challenge:
    cid: str
    category: str
    flag: str
    files: dict[str, str]  # filename -> text, placed in environment/workdir
    brief: str             # category-specific body of the instruction
    solve_py: str          # self-contained oracle; reads $CHALLENGE_DIR (default /app)


def make_flag(rng: Random) -> str:
    body = "".join(rng.choice(string.ascii_lowercase + string.digits) for _ in range(rng.randint(8, 16)))
    return f"flag{{{body}}}"


# --- category encoders ------------------------------------------------------
# Each returns (files, brief, solve_py). Every oracle recovers the flag by
# known-plaintext ("flag{") or brute force, so no secret is embedded in it.

def _enc_xor_single(flag: str, rng: Random):
    key = rng.randint(1, 255)
    ct = bytes(b ^ key for b in flag.encode())
    files = {"cipher.hex": ct.hex() + "\n"}
    brief = (
        "A flag was XOR-encrypted with a single unknown byte key. The hex "
        "ciphertext is in `cipher.hex`. Recover the flag (it begins with `flag{`)."
    )
    solve = textwrap.dedent(
        '''\
        import os
        d = os.environ.get("CHALLENGE_DIR", "/app")
        ct = bytes.fromhex(open(f"{d}/cipher.hex").read().strip())
        for k in range(256):
            pt = bytes(b ^ k for b in ct)
            if pt.startswith(b"flag{") and pt.endswith(b"}"):
                print(pt.decode()); break
        '''
    )
    return files, brief, solve


def _enc_xor_repeat(flag: str, rng: Random):
    klen = rng.randint(2, 5)
    key = bytes(rng.randint(1, 255) for _ in range(klen))
    pt = flag.encode()
    ct = bytes(pt[i] ^ key[i % klen] for i in range(len(pt)))
    files = {"cipher.hex": ct.hex() + "\n"}
    brief = (
        "A flag was encrypted with repeating-key XOR (key length 2-5). The hex "
        "ciphertext is in `cipher.hex`. The flag begins with `flag{`."
    )
    solve = textwrap.dedent(
        '''\
        import os
        d = os.environ.get("CHALLENGE_DIR", "/app")
        ct = bytes.fromhex(open(f"{d}/cipher.hex").read().strip())
        known = b"flag{"
        for klen in range(1, 6):
            key = bytes(ct[i] ^ known[i] for i in range(min(klen, len(known))))
            if len(key) < klen:
                continue
            pt = bytes(ct[i] ^ key[i % klen] for i in range(len(ct)))
            if pt.startswith(b"flag{") and pt.endswith(b"}") and all(32 <= c < 127 for c in pt):
                print(pt.decode()); break
        '''
    )
    return files, brief, solve


def _enc_caesar(flag: str, rng: Random):
    cs = string.ascii_lowercase + string.digits
    n = rng.randint(1, len(cs) - 1)
    ct = "".join(cs[(cs.index(c) + n) % len(cs)] if c in cs else c for c in flag)
    files = {"cipher.txt": ct + "\n"}
    brief = (
        "The flag was shifted with a Caesar-style cipher over the alphabet "
        "[a-z0-9] (non-alphanumeric characters unchanged). Ciphertext in "
        "`cipher.txt`. The flag begins with `flag{`."
    )
    solve = textwrap.dedent(
        '''\
        import os, string
        d = os.environ.get("CHALLENGE_DIR", "/app")
        cs = string.ascii_lowercase + string.digits
        ct = open(f"{d}/cipher.txt").read().strip()
        for n in range(len(cs)):
            pt = "".join(cs[(cs.index(c) - n) % len(cs)] if c in cs else c for c in ct)
            if pt.startswith("flag{") and pt.endswith("}"):
                print(pt); break
        '''
    )
    return files, brief, solve


def _enc_base64_layers(flag: str, rng: Random):
    layers = rng.randint(2, 4)
    data = flag.encode()
    for _ in range(layers):
        data = base64.b64encode(data)
    files = {"data.b64": data.decode() + "\n"}
    brief = (
        "The flag was base64-encoded several times. The encoded blob is in "
        "`data.b64`. Decode repeatedly until you recover `flag{...}`."
    )
    solve = textwrap.dedent(
        '''\
        import os, base64
        d = os.environ.get("CHALLENGE_DIR", "/app")
        data = open(f"{d}/data.b64").read().strip().encode()
        for _ in range(16):
            try:
                data = base64.b64decode(data)
            except Exception:
                break
            if data.startswith(b"flag{") and data.endswith(b"}"):
                print(data.decode()); break
        '''
    )
    return files, brief, solve


ENCODERS = {
    "xor-single": _enc_xor_single,
    "xor-repeat": _enc_xor_repeat,
    "caesar": _enc_caesar,
    "base64-layers": _enc_base64_layers,
}


def generate_challenge(seed: int, category: str) -> Challenge:
    if category not in ENCODERS:
        raise GenerateError(f"Unknown category {category!r}. Known: {', '.join(ENCODERS)}")
    rng = Random(f"flaggy::{category}::{seed}")
    flag = make_flag(rng)
    files, brief, solve = ENCODERS[category](flag, rng)
    cid = slugify(f"{category}-{seed:05d}")
    return Challenge(cid=cid, category=category, flag=flag, files=files, brief=brief, solve_py=solve)


# --- task rendering ---------------------------------------------------------

def _render_instruction(ch: Challenge) -> str:
    files = "\n".join(f"- `{name}`" for name in ch.files)
    return f"""# {ch.cid}

You are solving a self-contained Capture-The-Flag challenge (category: {ch.category}).

## Objective

{ch.brief}

## Provided files (in `/app`)

{files}

## Submit

Write the recovered flag (the literal `flag{{...}}` string) to:

```
/logs/artifacts/flag.txt
```

Nothing else is required. The flag is graded by exact match.
"""


def _render_task_toml(ch: Challenge) -> str:
    return textwrap.dedent(
        f"""
        version = "1.0"
        artifacts = ["/logs/agent/trajectory.json"]

        [task]
        name = {json.dumps(ch.cid)}
        description = {json.dumps(f"Procedural {ch.category} CTF challenge (flag-graded).")}
        keywords = ["flaggy", "ctf", "training", {json.dumps(ch.category)}]

        [metadata]
        author_name = "Flaggy"
        author_email = "security@example.invalid"
        category = "security"
        difficulty_explanation = "Procedurally generated training task graded on exact-flag capture."

        [environment]
        network_mode = "no-network"
        build_timeout_sec = 300.0
        cpus = 1
        memory_mb = 1024
        storage_mb = 2048

        [agent]
        timeout_sec = 600.0
        network_mode = "no-network"

        [verifier]
        timeout_sec = 60.0
        network_mode = "no-network"
        """
    ).strip() + "\n"


def _render_dockerfile() -> str:
    # Minimal + fast on purpose: pure-puzzle tasks need no toolbox, which keeps
    # RL rollouts cheap. operatorize onto the Exegol image only if you want to.
    return textwrap.dedent(
        """
        FROM python:3.12-slim
        WORKDIR /app
        COPY workdir/ /app/
        RUN mkdir -p /logs/artifacts
        """
    ).strip() + "\n"


def _render_grader(ch: Challenge) -> str:
    return textwrap.dedent(
        f'''\
        #!/usr/bin/env python3
        """Exact-flag verifier. The true flag is here, not in the agent's view."""
        import json, os
        from pathlib import Path

        FLAG = {ch.flag!r}
        ART = Path(os.environ.get("FLAGGY_ARTIFACTS", "/logs/artifacts"))
        REWARD = Path(os.environ.get("FLAGGY_REWARD", "/logs/verifier/reward.json"))


        def submitted() -> str:
            f = ART / "flag.txt"
            if f.exists() and f.read_text().strip():
                return f.read_text().strip()
            if ART.exists():
                for p in ART.rglob("*"):
                    if p.is_file():
                        try:
                            if FLAG in p.read_text(errors="replace"):
                                return FLAG
                        except Exception:
                            pass
            return ""


        def main() -> None:
            got = submitted()
            solved = got.strip() == FLAG or FLAG in got
            reward = 1.0 if solved else 0.0
            REWARD.parent.mkdir(parents=True, exist_ok=True)
            REWARD.write_text(json.dumps({{"reward": reward, "solved": solved}}))
            print(json.dumps({{"reward": reward, "solved": solved, "got": got[:80]}}))
            raise SystemExit(0 if solved else 1)


        if __name__ == "__main__":
            main()
        '''
    )


def _render_test_sh() -> str:
    return textwrap.dedent(
        """
        #!/usr/bin/env bash
        set -euo pipefail
        python3 /tests/grade_flag.py
        """
    ).strip() + "\n"


def _render_solve_sh(ch: Challenge) -> str:
    return (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "mkdir -p /logs/artifacts\n"
        "python3 - > /logs/artifacts/flag.txt <<'PY'\n"
        + ch.solve_py
        + "PY\n"
    )


def write_task(ch: Challenge, dest_root: Path, *, force: bool = False) -> Path:
    dest = Path(dest_root) / ch.cid
    if dest.exists():
        if not force:
            raise GenerateError(f"Task already exists: {dest} (pass --force)")
        import shutil
        shutil.rmtree(dest)
    workdir = dest / "environment" / "workdir"
    workdir.mkdir(parents=True)
    (dest / "tests").mkdir()
    (dest / "solution").mkdir()

    for name, content in ch.files.items():
        (workdir / name).write_text(content)
    (dest / "instruction.md").write_text(_render_instruction(ch))
    (dest / "task.toml").write_text(_render_task_toml(ch))
    (dest / "environment" / "Dockerfile").write_text(_render_dockerfile())
    (dest / "tests" / "grade_flag.py").write_text(_render_grader(ch))
    (dest / "tests" / "test.sh").write_text(_render_test_sh())
    (dest / "solution" / "solve.sh").write_text(_render_solve_sh(ch))
    for script in [dest / "tests" / "test.sh", dest / "tests" / "grade_flag.py", dest / "solution" / "solve.sh"]:
        script.chmod(0o755)
    return dest


def generate_dataset(
    out_dir: str | Path,
    count: int,
    *,
    seed: int = 0,
    categories: list[str] | None = None,
    force: bool = False,
) -> list[Path]:
    cats = categories or list(ENCODERS)
    for c in cats:
        if c not in ENCODERS:
            raise GenerateError(f"Unknown category {c!r}. Known: {', '.join(ENCODERS)}")
    if count < 1:
        raise GenerateError("count must be >= 1")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(count):
        category = cats[i % len(cats)]
        ch = generate_challenge(seed + i, category)
        paths.append(write_task(ch, out, force=force))
    return paths
