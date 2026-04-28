#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ROOT="$REPO_ROOT/dharmagpt"
SYSTEMD_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SERVICE_NAME="dharmagptbeta-server.service"
SERVICE_PATH="$SYSTEMD_DIR/$SERVICE_NAME"
UNIT_TEMPLATE="$REPO_ROOT/deploy/systemd/dharmagptbeta-server.service.template"
VENV_PYTHON="$APP_ROOT/.venv/bin/python"
VENV_PIP="$APP_ROOT/.venv/bin/pip"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/health}"

ensure_service_unit() {
  mkdir -p "$SYSTEMD_DIR"
  if [[ -f "$UNIT_TEMPLATE" ]]; then
    python3 - <<PY
from pathlib import Path

template = Path(r"$UNIT_TEMPLATE").read_text(encoding="utf-8")
unit = template.replace("{{REPO_ROOT}}", r"$REPO_ROOT")
Path(r"$SERVICE_PATH").write_text(unit, encoding="utf-8")
PY
  else
    cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=DharmaGPT beta FastAPI server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$APP_ROOT
EnvironmentFile=$APP_ROOT/.env
ExecStart=$APP_ROOT/.venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF
  fi
  systemctl --user daemon-reload
}

require_clean_repo() {
  if ! git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "Not inside a git repository: $REPO_ROOT" >&2
    exit 1
  fi

  if [[ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]]; then
    echo "Repo has local changes. Commit or stash them before deploying." >&2
    git -C "$REPO_ROOT" status --short >&2
    exit 1
  fi
}

update_code() {
  echo "Pulling latest code..."
  git -C "$REPO_ROOT" pull --ff-only
}

ensure_venv() {
  if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "Creating virtualenv at $APP_ROOT/.venv..."
    python3 -m venv "$APP_ROOT/.venv"
  fi

  echo "Installing Python dependencies..."
  "$VENV_PIP" install --upgrade pip
  "$VENV_PIP" install -r "$APP_ROOT/requirements.txt"
}

run_migrations() {
  if [[ ! -f "$APP_ROOT/.env" ]]; then
    echo "Missing $APP_ROOT/.env" >&2
    exit 1
  fi

  set -a
  # shellcheck disable=SC1090
  . "$APP_ROOT/.env"
  set +a

  echo "Running SQLite -> PostgreSQL migration..."
  "$VENV_PYTHON" "$APP_ROOT/scripts/migrate_sqlite_to_postgres.py"

  if [[ -n "${PINECONE_API_KEY:-}" ]]; then
    echo "Running local vector -> Pinecone migration..."
    "$VENV_PYTHON" "$APP_ROOT/scripts/migrate_local_vectors_to_pinecone.py" --create-index
  else
    echo "Skipping Pinecone migration because PINECONE_API_KEY is not set."
  fi
}

restart_service() {
  ensure_service_unit
  echo "Restarting $SERVICE_NAME..."
  systemctl --user enable --now "$SERVICE_NAME"
  systemctl --user restart "$SERVICE_NAME"
}

wait_for_health() {
  echo "Waiting for health check at $HEALTH_URL..."
  HEALTH_URL="$HEALTH_URL" "$VENV_PYTHON" - <<'PY'
import os
import sys
import time
from urllib.request import urlopen

url = os.environ["HEALTH_URL"]
for attempt in range(1, 31):
    try:
        with urlopen(url, timeout=5) as resp:
            if resp.status == 200:
                print("Health check passed.")
                sys.exit(0)
    except Exception:
        time.sleep(2)
print("Health check failed after 30 attempts.", file=sys.stderr)
sys.exit(1)
PY
}

main() {
  require_clean_repo
  update_code
  ensure_venv
  run_migrations
  restart_service
  wait_for_health
  systemctl --user status "$SERVICE_NAME" --no-pager --full || true
}

main "$@"
