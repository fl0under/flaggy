# bounty-pi-agent

A simple, hackable prototype for running **scoped, legal bug bounty / vulnerability research agents** with:

- **Pi** as the interactive model harness.
- **OpenRouter** for direct LLM calls where the controller needs a small planning/review step.
- **tmux** for native, inspectable multi-agent orchestration.
- **Docker / Exegol** as the default operator container.
- **Harbor** integration points for future benchmark runs, rollouts, and RL-style data collection.

The main design choice: no giant hardcoded workflow. The controller prepares scope-bounded prompts, starts isolated workspaces, records logs, and lets Pi + shell tools do the work.

## Safety boundary

This workbench is for authorized programs, VDPs, internal assets, local labs, and CTF-style practice only.

The scaffold deliberately refuses to operate without a scope file. The agent contract forbids denial of service, stealth, persistence, credential attacks, destructive changes, data exfiltration, and broad internet scanning.

## Repo map

```text
bbagent/                    Python controller package
configs/scope.example.yaml  explicit allowlist and forbidden action policy
configs/agents.example.yaml runtime/model/container settings
tasks/example.local.yaml    example local lab task
benchmarks/local-toy-web/   loopback-only toy benchmark service
benchmarks/harbor/          Harbor integration notes
pi-package/                 Pi skills/prompts skeleton
tmux/tmux.conf              tmux helper bindings
scripts/bbctl               repo-local bbctl wrapper (uv run)
scripts/monitor.py          tiny curses tmux monitor
scripts/ghidra-headless     headless Ghidra decompile helper
scripts/ghidra/             Ghidra post-scripts (DecompileToFile.py)
docker/controller.Dockerfile controller image with Pi + bbctl
docker/compose.yaml         optional Docker Compose controller
```

## Quick start: local, no Docker

This project uses [uv](https://docs.astral.sh/uv/) for all Python workflows.
`uv` creates the virtualenv and installs dependencies on first run, so there is
no separate `venv`/`pip` step.

```bash
uv sync

# Terminal 1: local lab
uv run python benchmarks/local-toy-web/app.py

# Terminal 2: validate scope and create a plan
scripts/bbctl scope-check configs/scope.example.yaml
scripts/bbctl prompt tasks/example.local.yaml
scripts/bbctl launch tasks/example.local.yaml --no-docker

tmux attach -t bb-local-lab
```

`scripts/bbctl` wraps `uv run`, so it transparently uses the project
environment. You can also call the installed console script directly with
`uv run bbctl ...`.

For an OpenRouter-generated plan:

```bash
cp .env.example .env
export OPENROUTER_API_KEY=sk-or-...
scripts/bbctl plan tasks/example.local.yaml --model anthropic/claude-sonnet-4.5
```

## Quick start: controller Docker image

```bash
cd bounty-pi-agent/docker
cp ../.env.example ../.env
# edit ../.env

docker compose build
docker compose run --rm controller bash

# inside the controller
bbctl scope-check configs/scope.example.yaml
bbctl launch tasks/example.local.yaml --no-docker
```

The compose file mounts `/var/run/docker.sock` so the controller can launch Exegol containers. That is convenient but equivalent to giving the container host-level power; remove that mount if you do not want nested Docker orchestration.

## Exegol mode

The default `configs/agents.example.yaml` image is `nwodtuhs/exegol:free`; switch to `light` or `web` in `configs/agents.example.yaml` if your Exegol setup has those images available.

```bash
scripts/install-exegol-my-resources.sh
scripts/bbctl launch tasks/example.local.yaml
```

That starts a tmux window with a transparent `docker run ...` command. If Pi is not installed in the Exegol image, the shell prints the prompt and drops you into bash. You can either install Pi through Exegol my-resources, use the controller image, or keep Pi outside the target container and attach shells manually.

## Reverse engineering / binary analysis

The agent runs with full shell access inside the operator container, so it can
use whatever is installed there (Ghidra, gdb, radare2, objdump, …). The repo
ships a small image-agnostic helper rather than a hardcoded RE workflow:

```bash
# Decompile every function to a readable C file the agent can read.
scripts/ghidra-headless ./challenge evidence/challenge.c
```

`ghidra-headless` locates `analyzeHeadless` on `PATH`, via `$GHIDRA_HOME`, or in
common Ghidra/Exegol install paths, and prints clear guidance if Ghidra is not
present in the container. The `reverse-engineering` Pi skill documents the same
pattern (plus raw `analyzeHeadless` usage) so the agent can adapt on its own.

Note: the default controller image (`python:3.12-slim`) is intentionally lean
and does **not** include Ghidra. Run RE work in an Exegol image that ships it,
or add Ghidra to your own controller image — see "Exegol mode" below.

## tmux monitoring

```bash
scripts/monitor.py bb-local-lab
scripts/bbctl status bb-local-lab
scripts/bbctl tail bb-local-lab 1 --lines 80
```

Optional tmux bindings:

```bash
cat tmux/tmux.conf >> ~/.tmux.conf
```

Inside tmux:

- `prefix + B` shows `bbctl status`.
- `prefix + L` tails the current pane in a popup.

## Scope files

A scope file is a strict allowlist:

```yaml
program: local-lab
allowed_targets:
  - name: toy-web
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

Every task points to a scope file and a named target. The prompt renderer injects the scope into the agent instructions.

## Pi package

The `pi-package/` directory is intentionally mostly skills/prompts rather than TypeScript extension code. This keeps the first version auditable and avoids locking the workbench to Pi internals.

Use the skills as patterns for:

- scoped scouting,
- evidence review,
- report writing.

Future Pi extension commands can shell out to `bbctl`:

- `/bb-status`
- `/bb-spawn <task>`
- `/bb-scope`
- `/bb-report`

## Harbor / benchmark plan

The useful benchmark metrics for this project are not “got shell”. They are:

- stayed in scope,
- produced reproducible evidence,
- minimized false positives,
- stopped before risky actions,
- wrote a clear report,
- used tools efficiently.

Start with local Docker labs and validators that grade the final report. Later, pipe run trajectories into Harbor for model/harness comparisons and rollout generation.

## Commands

```bash
bbctl scope-check <scope.yaml>
bbctl prompt <task.yaml>
bbctl plan <task.yaml> [--model openrouter/model]
bbctl launch <task.yaml> [--config configs/agents.example.yaml] [--no-docker]
bbctl status <tmux-session>
bbctl tail <tmux-session> <window> [--lines 120]
```

## Next implementation steps

1. Add a real Pi TypeScript extension once your installed Pi version is pinned.
2. Add a Docker network profile per bug bounty program so agents cannot accidentally leave scope.
3. Add validators for local benchmarks: report contains evidence, target is scoped, no forbidden action was logged.
4. Add a trajectory exporter from Pi session JSONL + tmux logs into Harbor manifests.
5. Add model-routing experiments: cheap scout model, stronger reviewer model, local RE-specialist model later.
