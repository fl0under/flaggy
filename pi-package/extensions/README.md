# Future Pi extension ideas

The first prototype keeps orchestration outside Pi using tmux and `bbctl` because that is transparent and easy to hack.

Useful future Pi extension commands:

- `/bb-status`: list tmux/Docker agent windows.
- `/bb-spawn <task>`: call `bbctl launch` and stream the new pane summary.
- `/bb-scope`: render the active scope and warn if missing.
- `/bb-report`: collect run logs and draft a report.

Implement these only after checking Pi's current TypeScript extension API in your installed version.
