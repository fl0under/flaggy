# Local toy web benchmark

This is a loopback-only, intentionally vulnerable service for testing the harness and report flow.

```bash
python benchmarks/local-toy-web/app.py
scripts/bbctl scope-check configs/scope.example.yaml
scripts/bbctl plan tasks/example.local.yaml
scripts/bbctl launch tasks/example.local.yaml --no-docker
```

Expected low-impact findings:

1. Missing common browser security headers on responses.
2. Reflected unescaped query parameter on `/echo?q=...`.
3. Verbose debug/version details on `/health`.

Keep this local. Do not point the scaffold at real targets until a scope file matches an authorized program policy.
