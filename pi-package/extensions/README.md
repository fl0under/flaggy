# Pi extension notes

No Pi extension is required for the current workflow.

Flaggy keeps the CLI small:

```bash
flaggy export <task.yaml>
flaggy interactive <harbor-task-dir> --tool pi
```

A future Pi extension would only need to help Pi discover `/app/instruction.md` and `/logs/artifacts/`; it should not reimplement Harbor execution, grading, tmux recording, or task lifecycle management.
