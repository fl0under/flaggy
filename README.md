# Flaggy

Flaggy is now intentionally small: it turns a scoped security-research task into a native Harbor task, then gets out of the way.

Use **Harbor + Terminus-2** for reproducible evals, traces, and future RL. Use **`flaggy interactive`** when you want to work in the exact same generated task environment yourself, optionally with Pi if it is installed in the image.

## Safety boundary

This repo is for authorized programs, internal assets, local labs, and CTF-style practice only.

Every task must point to an explicit scope file. The generated instructions and verifier emphasize low-risk work: passive inspection, code review, safe local reproduction, clear evidence, and no denial of service, stealth, persistence, credential attacks, destructive changes, data exfiltration, or broad internet scanning.

## Repo map

```text
bbagent/                    tiny Python package: scope/task parsing, Harbor export, interactive env
configs/scope.example.yaml  explicit allowlist and forbidden-action policy
configs/scope.ctf.example.yaml
tasks/example.local.yaml    example local web lab task
tasks/example.ctf.yaml      example binary/CTF-style task
benchmarks/local-toy-web/   loopback-only toy benchmark service
benchmarks/flaggy/          generated Harbor tasks
benchmarks/harbor/          Harbor workflow notes
docs/HARBOR_FIRST.md        architecture notes
pi-package/                 optional Pi prompts/skills, not an orchestration layer
operator/Dockerfile         Exegol-based operator image for Harbor + interactive
docs/CYBENCH.md             recipe: run Cybench (and similar) on the operator image
docs/TRAINING.md            SFT/RL strategy and contamination-free training pools
scripts/flaggy              repo-local uv wrapper
scripts/build-operator      build the Exegol operator image
scripts/operator-smoketest  check the operator image can host Terminus (tmux)
scripts/ghidra-headless     headless Ghidra decompile helper
scripts/ghidra/             Ghidra post-scripts
```

## Quick start

```bash
uv sync

# Validate a scope file.
scripts/flaggy check configs/scope.example.yaml

# Export a Flaggy task YAML to a native Harbor task directory.
scripts/flaggy export tasks/example.local.yaml --force

# Run the task with Harbor directly. Flaggy does not wrap this.
harbor run -p benchmarks/flaggy/local-toy-header-review -a terminus-2 -m <model>

# Or open the same generated environment yourself.
scripts/flaggy interactive benchmarks/flaggy/local-toy-header-review
```

`flaggy export` prints the native `harbor run` command after writing the task.

If you are running without `uv`, use:

```bash
PYTHONPATH=. python -m bbagent.cli export tasks/example.local.yaml --force
```

## Minimal commands

```bash
flaggy check <scope.yaml>
flaggy export <task.yaml> [--out benchmarks/flaggy] [--docker-image IMG] [--force]
flaggy interactive <task.yaml-or-harbor-task-dir> [--tool shell|pi] [--image IMG]
flaggy operatorize <task-dir-or-dataset-tree> [--image IMG] [--dry-run]
flaggy generate [--out datasets/flaggy-train] [--count N] [--seed S] [--categories ...]
```

That is deliberately the whole interface.

- `check` validates a scope allowlist.
- `export` writes a Harbor task directory.
- `interactive` builds the generated Harbor `environment/Dockerfile`, mounts the task instruction at `/app/instruction.md`, mounts logs/artifacts at `/logs`, and opens a shell or Pi inside that same environment.
- `operatorize` retargets external benchmark tasks onto the operator image (see above).
- `generate` writes a procedural, contamination-free CTF training pool (see below).

Everything else should be done with Harbor directly:

```bash
harbor run -p benchmarks/flaggy/local-toy-header-review -a terminus-2 -m <model>
harbor view ./jobs
harbor traces export --path ./jobs --recursive
```

## Generated Harbor task layout

`flaggy export` writes:

```text
benchmarks/flaggy/<task-id>/
  instruction.md
  task.toml
  INTERACTIVE.md
  environment/
    Dockerfile
    workdir/
      ... copied task files ...
  tests/
    test.sh
    grade_report.py
    flaggy_scope.json
  solution/
    solve.sh
```

The instruction tells agents to write final outputs under `/logs/artifacts/`:

```text
/logs/artifacts/report.md
/logs/artifacts/notes.md
/logs/artifacts/evidence/
```

The verifier writes `/logs/verifier/reward.json`, so Harbor/SkyRL can use the task as a reward-producing terminal workload.

## Interactive mode

Interactive mode is for manual or Pi-assisted work without inventing a second runtime.

```bash
scripts/flaggy interactive tasks/example.local.yaml --force
scripts/flaggy interactive benchmarks/flaggy/local-toy-header-review --tool shell
scripts/flaggy interactive benchmarks/flaggy/local-toy-header-review --tool pi
```

When given a YAML task, `interactive` exports it first. When given a generated Harbor task directory, it uses that directory as-is.

Artifacts are written to:

```text
benchmarks/flaggy/<task-id>/.interactive/logs/artifacts/
```

`--tool pi` runs `pi @/app/instruction.md` if `pi` is installed in the generated image. If not, it drops to bash in the same environment. To make Pi always available, use a base image that already contains Pi or edit the generated `environment/Dockerfile`.

Interactive mode maps Harbor `network_mode = "no-network"` to Docker `--network none`. For allowlisted/public tasks it uses Docker's default bridge network; Harbor remains the stricter runner for eval/RL runs.

## Operator image (Exegol)

For real reverse-engineering and bug-bounty work you usually want a full
offensive toolkit rather than the minimal generated environment. The `operator/`
image is [Exegol](https://exegol.com) plus a few Terminus/Harbor-friendly tweaks
(neutralised wrapper entrypoint, a clean deterministic bash prompt for tmux
screen-scraping, and tmux assertions). Build it **once** and reuse it; the Exegol
base is large (~30-50GB), so you do not want to rebuild it per task.

```bash
# Build the operator image once (add your extra tools in operator/Dockerfile).
scripts/build-operator                      # -> flaggy-operator:latest

# Verify it can host Terminus (PID 1 alive, exec works, tmux pane drivable).
scripts/operator-smoketest flaggy-operator:latest
```

Use it as the **Harbor agent environment** by writing it into the task's
`[environment].docker_image`:

```bash
flaggy export tasks/example.ctf.yaml --docker-image flaggy-operator:latest --force
harbor run -p benchmarks/flaggy/ctf-crackme-re -a terminus-2 -m <model>
```

Use the **same image** as your manual workbench, without a per-task rebuild
(the task workdir is mounted at `/app`):

```bash
flaggy interactive benchmarks/flaggy/ctf-crackme-re --image flaggy-operator:latest
```

Because Terminus only ever opens a tmux pane and sends keystrokes, and Exegol
already ships tmux, Terminus runs unmodified inside this image. For eval/RL runs,
pin a digest (`FROM nwodtuhs/exegol@sha256:...`) in `operator/Dockerfile` for
reproducibility.

### External benchmarks (Cybench, NYU CTF, …)

The CTF benchmarks the labs report on already have Harbor/Terminal-Bench
adapters, so they live in their own repos and Flaggy just runs against them.
Terminus runs *inside* each task container, so to use the operator toolbox you
retarget each generated task's base image:

```bash
# After running an adapter (e.g. harbor-framework/terminal-bench adapters/cybench):
flaggy operatorize /path/to/dataset/cybench --image flaggy-operator:latest
tb run --agent terminus --model <model> --dataset-path /path/to/dataset/cybench
```

`operatorize` rewrites only the final `FROM` of each `environment/Dockerfile`, so
challenge files and build steps are preserved. CTF grading is exact-flag capture,
giving a clean reward signal. See [docs/CYBENCH.md](docs/CYBENCH.md) for the full
recipe and caveats.

### Training pool (procedural, contamination-free)

You can't RL on Cybench and then evaluate on it. `flaggy generate` produces a
*disjoint* training pool of procedural CTF tasks — generated, not scraped, so
they never overlap with any eval benchmark — that run through the same harness:

```bash
flaggy generate --out datasets/flaggy-train --count 200 --seed 0
# every task is solvable: the oracle must capture all flags
tb run --agent oracle --dataset-path datasets/flaggy-train --no-rebuild
# then RL/SFT with Terminus; reward = exact-flag capture
```

Each task hides a unique `flag{...}` recoverable from the challenge files alone,
grades on exact match (clean RLVR reward), is deterministic by seed, and ships an
oracle solution (proof of solvability + ready-made SFT trajectories). Categories
(`xor-single`, `xor-repeat`, `caesar`, `base64-layers`) live in a registry in
`bbagent/generate.py` and are easy to extend. Train on this pool, keep
Cybench/NYU CTF held out. See [docs/TRAINING.md](docs/TRAINING.md) for the wider
SFT/RL strategy.

## Scope files

A scope file is a strict allowlist:

```yaml
program: local-lab
mode: local-lab
allowed_targets:
  - name: toy-web
    kind: web
    base_url: "http://127.0.0.1:8080"
allowed_networks:
  - "127.0.0.1/32"
forbidden_actions:
  - denial_of_service
  - credential_stuffing
  - persistence
  - stealth
  - data_exfiltration
  - destructive_changes
```

Targets can be web services, binaries, or host:port services:

```yaml
allowed_targets:
  - name: toy-web
    kind: web
    base_url: "http://127.0.0.1:8080"
  - name: crackme
    kind: binary
    path: ./challenges/crackme
  - name: pwn-remote
    kind: host
    host: 127.0.0.1
    port: 31337
```

For local/offline/CTF modes, exported Harbor tasks default to `network_mode = "no-network"`. For non-local tasks, Flaggy derives Harbor hostname allowlists where possible and keeps the fuller bounty-style scope in the instruction and verifier metadata.

## Reverse engineering helper

The repo keeps one small image-agnostic helper for binary analysis:

```bash
scripts/ghidra-headless ./challenge evidence/challenge.c
```

It locates `analyzeHeadless` on `PATH`, via `$GHIDRA_HOME`, or in common Ghidra/Exegol locations. The generated Harbor image does not force a full RE stack; add tools to `environment/Dockerfile` for the task that needs them.

## Pi package

`pi-package/` is just optional prompt/skill material. It is not the runtime controller.

The intended Pi workflow is:

```bash
scripts/flaggy export tasks/example.local.yaml --force
scripts/flaggy interactive benchmarks/flaggy/local-toy-header-review --tool pi
```

Inside the container, Pi reads `/app/instruction.md` and writes evidence/report files under `/logs/artifacts/`.
