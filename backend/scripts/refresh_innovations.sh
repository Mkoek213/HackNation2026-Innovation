#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo"
set -a
source ./.env
set +a

mkdir -p backend/.cache
printf '%s Starting innovation refresh\n' "$(date -Is)"
flock -n backend/.cache/innovation-refresh.lock \
    backend/.venv/bin/python backend/scripts/refresh_innovations.py "$@"
