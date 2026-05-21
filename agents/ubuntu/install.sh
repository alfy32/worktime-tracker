#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(realpath "$0")")" && pwd)"
SYNC_PY="$SCRIPT_DIR/sync.py"
CONFIG_DIR="$HOME/.config/worktime-tracker"
CONFIG_FILE="$CONFIG_DIR/config"
SYSTEMD_DIR="$HOME/.config/systemd/user"

# ── Load existing values for re-run UX ──────────────────────────
current_url=""
current_name=""
if [[ -f "$CONFIG_FILE" ]]; then
  current_url=$(grep '^WORKTIME_SERVER_URL=' "$CONFIG_FILE" | cut -d= -f2- || true)
  current_name=$(grep '^WORKTIME_COMPUTER_NAME=' "$CONFIG_FILE" | cut -d= -f2- || true)
fi
default_name="${current_name:-$(hostname)}"

# ── Prompts ──────────────────────────────────────────────────────
echo ""
echo "Work Time Tracker — Ubuntu Agent Installer"
echo "─────────────────────────────────────────"
echo ""

if [[ -n "$current_url" ]]; then
  read -rp "Server URL [$current_url]: " input_url
  SERVER_URL="${input_url:-$current_url}"
else
  read -rp "Server URL (e.g. http://192.168.1.10:8000): " SERVER_URL
fi

read -rp "Computer name [$default_name]: " input_name
COMPUTER_NAME="${input_name:-$default_name}"

if [[ -z "$SERVER_URL" ]]; then
  echo "Error: Server URL cannot be empty." >&2
  exit 1
fi

if [[ "$COMPUTER_NAME" == *" "* ]]; then
  echo "Error: Computer name cannot contain spaces." >&2
  exit 1
fi

# ── Write config ─────────────────────────────────────────────────
mkdir -p "$CONFIG_DIR"
cat > "$CONFIG_FILE" <<EOF
WORKTIME_SERVER_URL=$SERVER_URL
WORKTIME_COMPUTER_NAME=$COMPUTER_NAME
EOF
echo "Wrote $CONFIG_FILE"
chmod 600 "$CONFIG_FILE"

# ── Write systemd units ──────────────────────────────────────────
mkdir -p "$SYSTEMD_DIR"

cat > "$SYSTEMD_DIR/worktime-sync.service" <<EOF
[Unit]
Description=Work Time Tracker — sync login/lock events
After=network.target

[Service]
Type=oneshot
EnvironmentFile=%h/.config/worktime-tracker/config
ExecStart=/usr/bin/python3 "$SYNC_PY"
StandardOutput=journal
StandardError=journal
EOF

cat > "$SYSTEMD_DIR/worktime-sync.timer" <<EOF
[Unit]
Description=Work Time Tracker — sync timer

[Timer]
OnBootSec=1min
OnUnitActiveSec=5min
Unit=worktime-sync.service

[Install]
WantedBy=timers.target
EOF

echo "Wrote systemd unit files to $SYSTEMD_DIR"

# ── Enable and (re)start ─────────────────────────────────────────
systemctl --user daemon-reload
systemctl --user enable worktime-sync.timer
systemctl --user restart worktime-sync.timer
echo "Timer enabled and (re)started."

# ── Initial sync ─────────────────────────────────────────────────
echo ""
echo "Running initial sync..."
WORKTIME_SERVER_URL="$SERVER_URL" WORKTIME_COMPUTER_NAME="$COMPUTER_NAME" \
  python3 "$SYNC_PY"

echo ""
echo "Done."
echo "Next sync in ~1 min, then every 5 min."
echo "Logs: journalctl --user -u worktime-sync"
