# Running Cybench on the Exegol operator image

[Cybench](https://cybench.github.io/) is the CTF benchmark Anthropic reports in
its Claude system cards. The Terminal-Bench / Harbor project ships a Cybench
adapter that converts it into the standard task format, so Flaggy doesn't
reimplement the benchmark — it just (a) provides the Exegol-based operator
environment and (b) retargets the adapter's output onto it.

The flow is: **build the operator image once → generate Cybench tasks with the
upstream adapter → `flaggy operatorize` to swap each task onto the operator image
→ run with Terminus.** Because Terminus runs *inside* each task container,
swapping the task's base image is what gives the agent your toolbox.

## 0. Build and verify the operator image (once)

```bash
scripts/build-operator                       # -> flaggy-operator:latest
scripts/operator-smoketest flaggy-operator:latest
```

Add any extra tools you need to `operator/Dockerfile` before building. For
reproducible eval/RL runs, pin a digest (`FROM nwodtuhs/exegol@sha256:...`).

## 1. Generate Cybench tasks with the upstream adapter

The adapter lives in `harbor-framework/terminal-bench`, not in this repo —
benchmarks stay external, exactly as intended.

```bash
git clone https://github.com/harbor-framework/terminal-bench
cd terminal-bench
uv sync

# Clone Cybench, convert it, and apply the upstream fix-up patches.
uv run python adapters/cybench/run_adapter.py \
  --clone-cybench --apply-patches \
  --output-dir dataset/cybench
```

This writes one task folder per challenge under `dataset/cybench/`, each with its
own `environment/Dockerfile` (solver toolbox + challenge files) and, for some
challenges, target services.

## 2. Retarget the tasks onto the operator image

```bash
# Preview first.
flaggy operatorize /path/to/terminal-bench/dataset/cybench --dry-run

# Apply: rewrites the final FROM of each task's environment/Dockerfile.
flaggy operatorize /path/to/terminal-bench/dataset/cybench --image flaggy-operator:latest
```

`operatorize` only rewrites the base image, so the rest of each Dockerfile —
`apt-get install`, `COPY`ing the challenge in, etc. — is preserved. Multi-stage
Dockerfiles are flagged `(multi-stage: review)`: only the final stage is
retargeted, builder stages are left alone.

## 3. Validate, then run

Always re-check the oracle solutions after retargeting — swapping the toolbox can
occasionally change behaviour:

```bash
cd /path/to/terminal-bench

# Oracle: confirm the known solutions still capture the flag.
uv run tb run --agent oracle --dataset-path dataset/cybench --no-rebuild

# Real run with Terminus + your model, in the operator environment.
uv run tb run --agent terminus --model <provider/model> --dataset-path dataset/cybench

# A single challenge:
uv run tb run --agent terminus --model <provider/model> \
  --dataset-path dataset/cybench --task-id "<benchmark-name>"
```

(Grading is exact-flag capture, so you get a clean, ungameable reward — ideal for
model comparison and RL, unlike the report-rubric used for the local bounty tasks.)

## Caveats

- **Exegol is Kali/Debian-based (apt).** Cybench task Dockerfiles assume an
  apt-based agent image, so retargeting is compatible. A task that depended on a
  file the original base provided at a specific path could break — the oracle
  step in §3 is how you catch that.
- **Multi-service challenges.** `operatorize` only touches the solver
  `environment/Dockerfile`. Separate target services (defined in a compose file)
  are intentionally left as-is — Exegol is the attacker box, not the target.
- **Image size.** The Exegol base is large; pass `--no-rebuild` to the oracle
  run after the first build, and pre-pull the operator image on remote runners.
- **Scaling out.** Once one challenge runs end to end, add `--n-concurrent N` and
  a cloud `--env` (Daytona/Modal) to fan out, and point the same operator image
  at NYU CTF or other adapters the same way.
