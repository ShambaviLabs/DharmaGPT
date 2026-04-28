#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PG_ROOT="$REPO_ROOT/.local-postgres/root/usr/lib/postgresql/14/bin"
DATA_DIR="$REPO_ROOT/.local-postgres/data"

if [[ ! -x "$PG_ROOT/pg_ctl" ]]; then
  echo "Postgres binaries not found at $PG_ROOT"
  exit 1
fi

if [[ -f "$DATA_DIR/PG_VERSION" ]]; then
  "$PG_ROOT/pg_ctl" -D "$DATA_DIR" stop -m fast || true
fi
