#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="${HOME}/.exegol/my-resources/setup"
mkdir -p "$BASE/tmux" "$BASE/python3" "$BASE/zsh"
cp "$ROOT/tmux/tmux.conf" "$BASE/tmux/tmux.conf"
cat > "$BASE/python3/requirements.txt" <<'REQ'
pyyaml>=6.0.1
requests>=2.31.0
rich>=13.7.0
REQ
cat > "$BASE/zsh/aliases" <<'ALIASES'
alias bb='bbctl'
alias bb-status='bbctl status'
ALIASES
echo "Installed Exegol my-resources tmux/python/zsh snippets under $BASE"
