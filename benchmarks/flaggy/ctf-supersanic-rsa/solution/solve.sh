#!/usr/bin/env bash
set -euo pipefail
mkdir -p /logs/artifacts/evidence
cat > /logs/artifacts/report.md <<'EOF'
# ctf-supersanic-rsa

## Scope / authorization
This oracle placeholder confirms the Harbor task layout only. Replace it with a real safe oracle for this task.

## Summary
No issue found by the placeholder oracle.

## Reproduction steps
Not applicable.

## Evidence
Placeholder evidence only.

## Impact
None.

## Suggested remediation
None.
EOF
echo "placeholder oracle" > /logs/artifacts/evidence/oracle.txt
