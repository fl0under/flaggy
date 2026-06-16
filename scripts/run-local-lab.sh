#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec uv run --project "$ROOT" python "$ROOT/benchmarks/local-toy-web/app.py"
