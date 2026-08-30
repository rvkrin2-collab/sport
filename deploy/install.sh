#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/apps/sport"
VENV="$APP_DIR/.venv"
PORT="8911"

cd "$APP_DIR"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r requirements.txt
mkdir -p "$APP_DIR/data"

cat >/etc/systemd/system/sport.service <<EOF
[Unit]
Description=Sport dashboard FastAPI
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
ExecStart=$VENV/bin/uvicorn backend.main:app --host 127.0.0.1 --port $PORT
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/sport-update.service <<EOF
[Unit]
Description=Update Sport dashboard from GitHub
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$APP_DIR
ExecStart=/bin/bash -lc 'git pull --ff-only origin main && $VENV/bin/pip install -q -r requirements.txt && systemctl restart sport.service'
EOF

cat >/etc/systemd/system/sport-update.timer <<'EOF'
[Unit]
Description=Update Sport dashboard every 5 minutes

[Timer]
OnBootSec=1min
OnUnitActiveSec=5min
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now sport.service
systemctl enable --now sport-update.timer

# Replace the old static /sport mapping with the application proxy.
tailscale serve --https=443 --set-path=/sport off >/dev/null 2>&1 || true
tailscale serve --bg --https=443 --set-path=/sport "http://127.0.0.1:$PORT"

sleep 1
curl -fsS "http://127.0.0.1:$PORT/api/health"
echo
echo "Sport v0.2 is running: https://finsync-01.tail481831.ts.net/sport/"
