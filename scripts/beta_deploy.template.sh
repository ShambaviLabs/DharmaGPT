#!/usr/bin/env bash
# DharmaGPT beta deploy template
# Copy to scripts/beta_deploy.sh, fill in the vars below, then run.
# (beta_deploy.sh is gitignored — keep server details off GitHub)
set -euo pipefail

BETA_HOST="user@your-beta-server"   # SSH target
REPO_PATH="/path/to/DharmaGPT"      # Repo root on beta server
BRANCH="main"

echo "==> Deploying DharmaGPT to beta ($BETA_HOST) ..."

ssh "$BETA_HOST" bash <<EOF
  set -euo pipefail
  cd "$REPO_PATH"

  echo "--- Pulling $BRANCH ---"
  git fetch origin
  git checkout $BRANCH
  git pull origin $BRANCH

  echo "--- Installing dependencies ---"
  dharmagpt/.venv/bin/pip install -q -r dharmagpt/requirements.txt

  echo "--- Restarting FastAPI ---"
  sudo systemctl restart dharmagpt-api

  echo "--- Restarting MCP server ---"
  sudo systemctl restart dharmagpt-mcp

  echo "--- Status ---"
  sudo systemctl status dharmagpt-api --no-pager -l | tail -5
  sudo systemctl status dharmagpt-mcp --no-pager -l | tail -5
EOF

echo "==> Deploy complete."
echo "    API : https://your-domain/docs"
echo "    MCP : http://your-domain:8001"
