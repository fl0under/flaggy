---
name: reverse-engineering
description: Static / headless binary analysis with Ghidra and standard RE tooling.
---

Use this skill for authorized binary reverse engineering: CTF practice, local
labs, or in-scope binaries you are explicitly allowed to analyze.

You have full shell access inside the operator container. Enumerate what is
actually installed before assuming a tool is missing:

```bash
command -v ghidra analyzeHeadless gdb objdump readelf strings nm file radare2 r2 2>/dev/null || true
```

Fast triage first:

```bash
file ./challenge
strings -n 6 ./challenge | head
readelf -h ./challenge
objdump -d ./challenge | head -100
```

Headless Ghidra decompilation (non-interactive, agent-friendly output):

```bash
# Convenience wrapper: import + analyze + decompile every function to a C file.
/workspace/scripts/ghidra-headless ./challenge evidence/challenge.c

# Or drive analyzeHeadless directly when you need custom scripts/options:
analyzeHeadless /tmp/proj bbagent_re -import ./challenge \
  -scriptPath /workspace/scripts/ghidra \
  -postScript DecompileToFile.py evidence/challenge.c -deleteProject
```

Then read `evidence/challenge.c`, identify interesting functions, and only drop
to interactive `gdb`/Ghidra GUI if static analysis is not enough.

Discipline:

- Record exact commands, tool versions, and output paths.
- Keep decompilation and evidence under the run or `evidence/` directory.
- Separate observed fact from inference; mark confidence and missing evidence.
- Stay within the authorized scope; never exfiltrate or run destructive actions.
