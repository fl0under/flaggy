# Agent operating contract

This repo is for legal, authorized bug bounty / vulnerability research only.

When acting as an agent:

1. Load and obey the active `scope.yaml` before touching any target.
2. Treat missing scope as a hard stop.
3. Prefer passive inspection, code review, safe local reproduction, and evidence gathering.
4. Do not run denial-of-service, stealth, persistence, credential attacks, broad internet scans, destructive actions, or data exfiltration.
5. Stop before state-changing actions and ask for human approval.
6. Record commands, observations, timestamps, and evidence paths.
7. Reports should separate: observed fact, security impact, reproduction, recommended fix, uncertainty.

Good output beats clever exploitation: the first benchmark metric is useful, low-false-positive reports.
