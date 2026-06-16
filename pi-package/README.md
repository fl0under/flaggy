# Pi prompts and skills

This directory contains optional Pi prompt/skill material. It is not a controller and it does not own the runtime.

Preferred workflow:

```bash
scripts/flaggy export tasks/example.local.yaml --force
scripts/flaggy interactive benchmarks/flaggy/local-toy-header-review --tool pi
```

`flaggy interactive --tool pi` builds the generated Harbor environment, mounts the instruction at `/app/instruction.md`, mounts artifacts at `/logs/artifacts`, and runs:

```bash
pi @/app/instruction.md
```

If Pi is not installed in that image, the launcher drops to bash in the same environment. To make Pi always available, use a base image with Pi or edit the generated `environment/Dockerfile`.

The skills are useful patterns for:

- scoped scouting,
- evidence review,
- report writing,
- reverse-engineering triage.
