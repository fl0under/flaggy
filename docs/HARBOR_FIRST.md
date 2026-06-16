# Harbor-first architecture

Flaggy has one job: compile a scoped security-research task into a Harbor task directory.

After that:

- Harbor runs reproducible eval/RL/SFT workloads.
- Terminus-2 is the default Harbor terminal agent.
- `flaggy interactive` opens the same generated environment for manual or Pi-assisted work.

There is no custom Harbor runner, no tmux recorder, no local grading wrapper, and no backwards-compatible legacy command layer.

## Workflow

```bash
scripts/flaggy check configs/scope.example.yaml
scripts/flaggy export tasks/example.local.yaml --force

harbor run \
  -p benchmarks/flaggy/local-toy-header-review \
  -a terminus-2 \
  -m <model>

scripts/flaggy interactive benchmarks/flaggy/local-toy-header-review --tool shell
scripts/flaggy interactive benchmarks/flaggy/local-toy-header-review --tool pi
```

## Minimal CLI surface

```bash
flaggy check <scope.yaml>
flaggy export <task.yaml> [--out benchmarks/flaggy] [--force]
flaggy interactive <task-yaml-or-harbor-task-dir> [--tool shell|pi]
```

Harbor commands stay native:

```bash
harbor run -p <task-dir> -a terminus-2 -m <model>
harbor view ./jobs
harbor traces export --path ./jobs --recursive
```

## Generated Harbor task layout

```text
benchmarks/flaggy/<task-id>/
  instruction.md
  task.toml
  INTERACTIVE.md
  environment/
    Dockerfile
    workdir/
  tests/
    test.sh
    grade_report.py
    flaggy_scope.json
  solution/
    solve.sh
```

Agents write outputs to `/logs/artifacts/`:

```text
/logs/artifacts/report.md
/logs/artifacts/notes.md
/logs/artifacts/evidence/
```

The verifier writes `/logs/verifier/reward.json`.

## What remains custom

Only the Flaggy-specific bits remain:

- scope/task validation,
- bounty-style scope → Harbor instruction/network/verifier metadata,
- report/evidence reward rubric,
- optional interactive Docker launcher using the same Harbor environment,
- small helper scripts such as `scripts/ghidra-headless`.

## Interactive mode

`flaggy interactive` builds `environment/Dockerfile` from the generated Harbor task and mounts:

```text
/app/instruction.md      read-only task instruction
/logs                   local .interactive/logs directory
```

`--tool shell` opens bash.

`--tool pi` runs `pi @/app/instruction.md` when `pi` is installed in the image, otherwise it drops to bash. To make Pi always available, use a base image that already contains Pi or edit the generated Dockerfile.

For offline/local tasks, Harbor `network_mode = "no-network"` maps to Docker `--network none` in interactive mode. For allowlisted/public tasks, interactive mode uses Docker's default bridge network because Docker alone does not provide Harbor's hostname allowlist semantics.

## RL path

```text
Flaggy task YAML
  -> flaggy export
  -> Harbor task directory
  -> harbor run -a terminus-2
  -> Harbor artifacts + trajectory + reward.json
  -> Harbor traces/SkyRL integration
```

Keep Pi as an interactive assistant unless you later write a real Harbor custom-agent adapter for it that emits the trajectory and token metadata needed for training.
