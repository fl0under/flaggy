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

## Driving interactive gdb from your own shell

Your shell tool spawns one subprocess per call with no persistent stdin, so
running `gdb ./challenge` directly will just hang waiting for input. Instead,
run gdb in its own tmux pane and drive it with `send-keys`/`capture-pane`:

```bash
# Split the current window and start gdb in the new pane.
tmux split-window -t "$TMUX_PANE" -d "gdb ./challenge"

# Find the pane you just created (window_name.pane_index).
tmux list-panes -F "#{window_name}.#{pane_index} #{pane_current_command}"

# Send a command (C-m submits it, like pressing Enter).
tmux send-keys -t mytask.1 "break main" C-m
tmux send-keys -t mytask.1 "run" C-m

# Read back what gdb printed so far.
tmux capture-pane -p -t mytask.1 -S -200
```

This read/write round-trip (write with `send-keys`, read with
`capture-pane`) is the general pattern for any interactive program you need
to script from outside — gdb, a custom REPL, an interactive exploit, etc.

The background recorder started by `bbctl launch` already polls every pane in
the session (not just the original window), so once you create the gdb pane
it will automatically show up in `transcript.log` tagged with its
`window.pane` target — no extra steps needed to capture it as evidence.

Caveat: this only works when your shell is directly inside the host tmux
session, i.e. `bbctl launch --no-docker`. In normal (Docker) launch mode the
agent runs inside a container with no docker socket or tmux socket mounted,
so it cannot see or attach to the host tmux session — `tmux` commands won't
find the launch session at all in that mode.

Discipline:

- Record exact commands, tool versions, and output paths.
- Keep decompilation and evidence under the run or `evidence/` directory.
- Separate observed fact from inference; mark confidence and missing evidence.
- Stay within the authorized scope; never exfiltrate or run destructive actions.
