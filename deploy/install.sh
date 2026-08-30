#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/apps/sport"
VENV="$APP_DIR/.venv"
PORT="8911"

cd "$APP_DIR"

if ! python3 -m venv --help >/dev/null 2>&1; then
  apt-get update
  apt-get install -y python3-venv
fi

python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r requirements.txt
mkdir -p "$APP_DIR/data"
chmod 700 "$APP_DIR/data"

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

# Replace only the /sport mapping. Existing /, /chinese and /portfolio stay untouched.
tailscale serve --https=443 --set-path=/sport off >/dev/null 2>&1 || true
tailscale serve --bg --https=443 --set-path=/sport "http://127.0.0.1:$PORT"

for i in {1..20}; do
  if curl -fsS "http://127.0.0.1:$PORT/api/health"; then
    echo
    break
  fi
  sleep 1
  if [ "$i" -eq 20 ]; then
    echo "sport.service did not become healthy" >&2
    systemctl status sport.service --no-pager || true
    journalctl -u sport.service -n 80 --no-pager || true
    exit 1
  fi
done

echo "Sport v0.2 is running: https://finsync-01.tail481831.ts.net/sport/"
