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

`launch` starts a background recorder that tails the tmux window into
`runs/<run_id>/transcript.log` for as long as the window exists (skip it with
`--no-record`). When the agent is done:

```bash
scripts/bbctl report runs/<run_id>     # draft report.md from events + evidence + transcript
scripts/bbctl grade runs/<run_id>      # score the run against completeness/scope checks
scripts/bbctl grade runs/<run_id> --write --json
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

The controller image (`docker/controller.Dockerfile`) ships Ghidra (headless),
a JDK, and `binutils`/`file`/`gdb`, so the simplest RE setup is to run the agent
inside it:

```bash
docker compose -f docker/compose.yaml run --rm controller bash
# inside the controller (Pi runs here, tools are local):
bbctl launch tasks/example.ctf.yaml --no-docker
scripts/ghidra-headless ./challenges/crackme evidence/crackme.c
```

Pin a different Ghidra release at build time with
`--build-arg GHIDRA_VERSION=... --build-arg GHIDRA_DATE=...`. Exegol images that
already ship Ghidra work too.

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

Targets come in three kinds. `kind` defaults to `web` for backward
compatibility:

```yaml
allowed_targets:
  - name: toy-web                 # web service (default kind)
    kind: web
    base_url: "http://127.0.0.1:8080"
  - name: crackme                 # local binary to reverse engineer
    kind: binary
    path: ./challenges/crackme
  - name: pwn-remote              # host:port service (e.g. CTF pwn)
    kind: host
    host: 127.0.0.1
    port: 31337
```

- `web` targets are enforced for HTTP egress via `assert_url_allowed`.
- `host` targets are enforced via `assert_host_allowed(host, port)`.
- `binary` targets name a local file the agent is authorized to analyze.

See `configs/scope.ctf.example.yaml` + `tasks/example.ctf.yaml` for a
reverse-engineering example. Every task points to a scope file and a named
target; the prompt renderer injects the scope into the agent instructions.

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

`bbctl grade` runs the local validators today: task/window/transcript present,
evidence present, report present and free of leftover `TODO`s, and a
regex-based scope check over the recorded transcript (flags URLs outside the
scope's allowed targets/networks). It's a best-effort, post-hoc signal, not a
security control — see the printed notes for its limitations. `grade.json` is
shaped for a future Harbor manifest / trajectory exporter.

## Commands

```bash
bbctl scope-check <scope.yaml>
bbctl prompt <task.yaml>
bbctl plan <task.yaml> [--model openrouter/model]
bbctl launch <task.yaml> [--config configs/agents.example.yaml] [--no-docker] [--no-record]
bbctl status <tmux-session>
bbctl tail <tmux-session> <window> [--lines 120]
bbctl record <run_dir> <session> [--target window.pane ...] [--interval 5] [--lines 2000]
bbctl report <run_dir>
bbctl grade <run_dir> [--write] [--json]
```

`record` is started automatically by `launch` as a detached background
process; you'd only run it directly to re-attach logging to a session that was
started without one. By default it polls and tails *every* pane in the
session, re-discovering panes on each poll, so a pane the agent opens mid-task
(e.g. `tmux split-window ... gdb ./challenge`, see the `reverse-engineering`
skill) is picked up automatically and folded into `transcript.log` with a
`[window.pane]` tag — pass `--target` one or more times to record only
specific panes instead. This only sees panes inside the launch tmux session,
which means it only works in `--no-docker` mode; in Docker launch mode the
agent's container has no tmux socket mounted, so panes it might want to open
for interactive tools live outside the host session and are not recorded.

## Next implementation steps

1. Add a real Pi TypeScript extension once your installed Pi version is pinned.
2. Enforce scope at runtime (network policy or a scoped egress proxy) instead of only advising it in the prompt — today nothing stops an agent from leaving scope.
3. Add a trajectory exporter from run logs (events.jsonl + transcript.log) into Harbor manifests, feeding `grade.json` in as a reward signal.
4. Add model-routing experiments: cheap scout model, stronger reviewer model, local RE-specialist model later.
