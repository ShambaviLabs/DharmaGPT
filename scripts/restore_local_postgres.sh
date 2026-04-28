#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PG_ROOT="$REPO_ROOT/.local-postgres/root/usr/lib/postgresql/14/bin"
PORT="${POSTGRES_PORT:-5433}"
DB_NAME="${POSTGRES_DB:-dharmagpt}"
BACKUP_FILE="${1:-}"

if [[ -z "$BACKUP_FILE" ]]; then
  echo "Usage: $0 <backup.dump>"
  exit 1
fi

if [[ ! -f "$BACKUP_FILE" ]]; then
  echo "Backup file not found: $BACKUP_FILE"
  exit 1
fi

if [[ ! -x "$PG_ROOT/pg_restore" ]]; then
  echo "pg_restore not found at $PG_ROOT"
  exit 1
fi

"$PG_ROOT/pg_restore" -h 127.0.0.1 -p "$PORT" -U postgres --clean --if-exists --no-owner -d "$DB_NAME" "$BACKUP_FILE"
