# pi-bounty-workbench

A lightweight Pi package skeleton. It deliberately uses skills/prompts first because they are easier to inspect and modify than a hardcoded workflow.

Suggested use:

1. Copy or symlink `skills/` and `prompts/` into your Pi package path.
2. Start Pi from the repo root so `AGENTS.md`, `configs/`, `tasks/`, and run logs are in context.
3. Use `scripts/bbctl prompt tasks/example.local.yaml` to render a bounded task prompt.

The `extensions/` directory contains notes for a future live monitor command, but the first prototype uses tmux + `scripts/monitor.py` instead.
