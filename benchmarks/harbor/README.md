# Harbor workflow

Flaggy exports native Harbor tasks and then gets out of the way.

```bash
scripts/flaggy export tasks/example.local.yaml --force
harbor run -p benchmarks/flaggy/local-toy-header-review -a terminus-2 -m <model>
```

Generated layout:

```text
benchmarks/flaggy/local-toy-header-review/
  instruction.md
  task.toml
  INTERACTIVE.md
  environment/Dockerfile
  environment/workdir/app.py
  tests/test.sh
  tests/grade_report.py
  solution/solve.sh
```

The verifier expects agents to write final outputs under `/logs/artifacts/` and produces `/logs/verifier/reward.json` with a scalar `reward` plus named component checks.

For manual/Pi-assisted work in the same environment:

```bash
scripts/flaggy interactive benchmarks/flaggy/local-toy-header-review --tool shell
scripts/flaggy interactive benchmarks/flaggy/local-toy-header-review --tool pi
```

Do not use fully autonomous Harbor/Terminus runs against live public targets unless authorization, scope, and external human approval gates are explicit.
