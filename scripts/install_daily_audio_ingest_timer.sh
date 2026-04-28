#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYSTEMD_DIR="$HOME/.config/systemd/user"
SERVICE="$SYSTEMD_DIR/dharmagpt-daily-audio-ingest.service"
TIMER="$SYSTEMD_DIR/dharmagpt-daily-audio-ingest.timer"
RUN_AT="${DAILY_AUDIO_RUN_AT:-03:30}"

mkdir -p "$SYSTEMD_DIR"
mkdir -p "$REPO_ROOT/dharmagpt/knowledge/incoming/audio"

cat > "$SERVICE" <<EOF
[Unit]
Description=DharmaGPT daily one-audio Pinecone ingestion
After=network-online.target dharmagptbeta-server.service

[Service]
Type=oneshot
WorkingDirectory=$REPO_ROOT/dharmagpt
EnvironmentFile=$REPO_ROOT/dharmagpt/.env
ExecStart=$REPO_ROOT/dharmagpt/.venv/bin/python $REPO_ROOT/dharmagpt/scripts/daily_audio_ingest.py
EOF

cat > "$TIMER" <<EOF
[Unit]
Description=Run DharmaGPT daily one-audio Pinecone ingestion

[Timer]
OnCalendar=*-*-* $RUN_AT:00
Persistent=true
RandomizedDelaySec=15m
Unit=dharmagpt-daily-audio-ingest.service

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now dharmagpt-daily-audio-ingest.timer

echo "Installed daily audio ingest timer at $RUN_AT."
echo "Drop pending audio files in: $REPO_ROOT/dharmagpt/knowledge/incoming/audio"
systemctl --user list-timers dharmagpt-daily-audio-ingest.timer --no-pager
