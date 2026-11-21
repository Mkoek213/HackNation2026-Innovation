#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo"
set -a
source ./.env
set +a

# cron has a bare PATH; the Codex CLI usually lives in ~/.local/bin.
export PATH="$HOME/.local/bin:$PATH"
# Assess with the local Codex subscription when present, so Gemini credits stay for the app.
export ASSESS_ENGINE="${ASSESS_ENGINE:-$(command -v codex >/dev/null && echo codex || echo gemini)}"

mkdir -p backend/.cache
printf '%s Starting innovation refresh\n' "$(date -Is)"
flock -n backend/.cache/innovation-refresh.lock bash -c '
    backend/.venv/bin/python backend/scripts/refresh_innovations.py "$@"
    # New cards get the FAQ assessment in the same run; a dry run publishes nothing to assess.
    [[ " $* " == *" --dry-run "* ]] || backend/.venv/bin/python backend/scripts/assess_innovations.py --engine "$ASSESS_ENGINE"
' refresh "$@"
