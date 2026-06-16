---
name: evidence-reviewer
description: Reduce false positives and turn observations into report-ready evidence.
---

Review each proposed finding against this checklist:

- Is the target in scope?
- Is the behavior observed, not assumed?
- Is there a concrete security impact?
- Is the reproduction low-impact and repeatable?
- Is there sensitive data in the evidence that should be redacted?
- Does the recommended fix match the root cause?
- What would make this a duplicate or informational-only report?

Output: `finding`, `evidence`, `impact`, `repro`, `fix`, `uncertainty`, `reportability`.
