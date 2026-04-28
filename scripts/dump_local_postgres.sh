#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PG_ROOT="$REPO_ROOT/.local-postgres/root/usr/lib/postgresql/14/bin"
BACKUP_DIR="$REPO_ROOT/.local-postgres/backups"
PORT="${POSTGRES_PORT:-5433}"
DB_NAME="${POSTGRES_DB:-dharmagpt}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_FILE="$BACKUP_DIR/${DB_NAME}-${TS}.dump"

mkdir -p "$BACKUP_DIR"

if [[ ! -x "$PG_ROOT/pg_dump" ]]; then
  echo "pg_dump not found at $PG_ROOT"
  exit 1
fi

"$PG_ROOT/pg_dump" -h 127.0.0.1 -p "$PORT" -U postgres -Fc "$DB_NAME" -f "$OUT_FILE"
echo "$OUT_FILE"
