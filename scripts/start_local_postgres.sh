#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PG_ROOT="$REPO_ROOT/.local-postgres/root/usr/lib/postgresql/14/bin"
DATA_DIR="$REPO_ROOT/.local-postgres/data"
SOCKET_DIR="$REPO_ROOT/.local-postgres/run"
LOG_FILE="$REPO_ROOT/.local-postgres/postgres.log"
PORT="${POSTGRES_PORT:-5433}"
DB_NAME="${POSTGRES_DB:-dharmagpt}"
DB_ADMIN_USER="${POSTGRES_ADMIN_USER:-$(whoami)}"
REMOTE_CLIENT_IP="${POSTGRES_REMOTE_CLIENT_IP:-}"
REMOTE_USER="${POSTGRES_REMOTE_USER:-dharmagpt_remote}"
REMOTE_PASSWORD_FILE="$REPO_ROOT/.local-postgres/remote_password.txt"
REMOTE_ENV_FILE="$REPO_ROOT/.local-postgres/remote_access.env"
ADVERTISE_HOST="${POSTGRES_ADVERTISE_HOST:-}"

if [[ -z "$ADVERTISE_HOST" ]]; then
  if [[ -n "$REMOTE_CLIENT_IP" ]]; then
    ADVERTISE_HOST="0.0.0.0"
  else
    ADVERTISE_HOST="127.0.0.1"
  fi
fi

if [[ ! -x "$PG_ROOT/initdb" ]]; then
  echo "Postgres binaries not found at $PG_ROOT"
  exit 1
fi

mkdir -p "$REPO_ROOT/.local-postgres"
mkdir -p "$SOCKET_DIR"

if [[ ! -f "$DATA_DIR/PG_VERSION" ]]; then
  mkdir -p "$DATA_DIR"
  "$PG_ROOT/initdb" -D "$DATA_DIR" --auth=trust --encoding=UTF8 --locale=C
fi

if ! "$PG_ROOT/pg_isready" -h 127.0.0.1 -p "$PORT" >/dev/null 2>&1; then
  "$PG_ROOT/pg_ctl" -D "$DATA_DIR" -l "$LOG_FILE" -o "-p $PORT -c listen_addresses=$ADVERTISE_HOST -c unix_socket_directories=$SOCKET_DIR -c unix_socket_permissions=0700" start
fi

if ! "$PG_ROOT/psql" -h 127.0.0.1 -p "$PORT" -U "$DB_ADMIN_USER" -d postgres -Atqc "SELECT 1 FROM pg_roles WHERE rolname = 'postgres'" | grep -q 1; then
  "$PG_ROOT/psql" -h 127.0.0.1 -p "$PORT" -U "$DB_ADMIN_USER" -d postgres -v ON_ERROR_STOP=1 -c "CREATE ROLE postgres LOGIN SUPERUSER;"
fi

if ! "$PG_ROOT/psql" -h 127.0.0.1 -p "$PORT" -U postgres -d postgres -Atqc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1; then
  "$PG_ROOT/createdb" -h 127.0.0.1 -p "$PORT" -U postgres "$DB_NAME"
fi

if [[ -n "$REMOTE_CLIENT_IP" ]]; then
  if [[ ! -f "$REMOTE_PASSWORD_FILE" ]]; then
    python3 - <<'PY' > "$REMOTE_PASSWORD_FILE"
import secrets
print(secrets.token_urlsafe(24))
PY
    chmod 600 "$REMOTE_PASSWORD_FILE"
  fi

  REMOTE_PASSWORD="$(tr -d '\n' < "$REMOTE_PASSWORD_FILE")"
  HBA_BLOCK="# BEGIN dharmagpt remote access"
  HBA_END="# END dharmagpt remote access"
  HBA_FILE="$DATA_DIR/pg_hba.conf"

  if ! grep -q "$HBA_BLOCK" "$HBA_FILE"; then
    cat <<EOF >> "$HBA_FILE"

$HBA_BLOCK
host    $DB_NAME    $REMOTE_USER    ${REMOTE_CLIENT_IP}/32    scram-sha-256
$HBA_END
EOF
  fi

  if ! "$PG_ROOT/psql" -h 127.0.0.1 -p "$PORT" -U postgres -d postgres -Atqc "SELECT 1 FROM pg_roles WHERE rolname = '$REMOTE_USER'" | grep -q 1; then
    "$PG_ROOT/psql" -h 127.0.0.1 -p "$PORT" -U postgres -d postgres -v ON_ERROR_STOP=1 -c "CREATE ROLE $REMOTE_USER LOGIN PASSWORD '$REMOTE_PASSWORD';"
  else
    "$PG_ROOT/psql" -h 127.0.0.1 -p "$PORT" -U postgres -d postgres -v ON_ERROR_STOP=1 -c "ALTER ROLE $REMOTE_USER PASSWORD '$REMOTE_PASSWORD';"
  fi

  "$PG_ROOT/psql" -h 127.0.0.1 -p "$PORT" -U postgres -d "$DB_NAME" -v ON_ERROR_STOP=1 <<SQL
GRANT CONNECT ON DATABASE $DB_NAME TO $REMOTE_USER;
GRANT USAGE ON SCHEMA public TO $REMOTE_USER;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO $REMOTE_USER;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO $REMOTE_USER;
SQL

  ADVERTISE_IP="${POSTGRES_ADVERTISE_IP:-$(hostname -I | awk '{print $1}') }"
  ADVERTISE_IP="${ADVERTISE_IP%% }"
  cat > "$REMOTE_ENV_FILE" <<EOF
DATABASE_URL=postgresql://$REMOTE_USER:$REMOTE_PASSWORD@$ADVERTISE_IP:$PORT/$DB_NAME
REMOTE_CLIENT_IP=$REMOTE_CLIENT_IP
REMOTE_USER=$REMOTE_USER
REMOTE_PASSWORD=$REMOTE_PASSWORD
EOF
  chmod 600 "$REMOTE_ENV_FILE"

  "$PG_ROOT/pg_ctl" -D "$DATA_DIR" reload
  echo "Remote access configured for $REMOTE_CLIENT_IP"
  echo "Remote connection info saved to $REMOTE_ENV_FILE"
fi

export DATABASE_URL="postgresql://postgres@127.0.0.1:${PORT}/${DB_NAME}"
echo "Postgres is ready: $DATABASE_URL"
