---
name: scoped-bounty-scout
description: Safe reconnaissance and hypothesis generation for authorized targets.
---

Use this skill when the current task instruction includes an explicit scope.

Process:

1. Restate the scope and target in one paragraph.
2. List the safest observations to collect first: headers, robots/sitemap, app routes, public docs, local source files, package manifests, version banners.
3. Use low-volume requests only. Never fuzz, brute force, spray, DoS, bypass auth, or touch third parties.
4. Convert observations into hypotheses. Mark confidence and missing evidence.
5. Stop before any state-changing request and request human approval.
6. Write notes and evidence under `/logs/artifacts/`.
