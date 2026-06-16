# Interactive use

This directory is a native Harbor task. Run eval/RL trials with Harbor directly:

```bash
harbor run -p benchmarks/flaggy/local-toy-header-review -a terminus-2 -m <model>
```

To work in the same generated environment yourself:

```bash
flaggy interactive benchmarks/flaggy/local-toy-header-review --tool shell
flaggy interactive benchmarks/flaggy/local-toy-header-review --tool pi
```

Inside the container:

- task instruction: `/app/instruction.md`
- final report: `/logs/artifacts/report.md`
- notes: `/logs/artifacts/notes.md`
- evidence: `/logs/artifacts/evidence/`

`--tool pi` runs `pi @/app/instruction.md` if Pi is installed in the image,
otherwise it opens bash in the same task environment.
