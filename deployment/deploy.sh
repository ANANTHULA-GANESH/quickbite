#!/usr/bin/env bash
# Redeploy QuickBite after you change the code. Keeps the environment file and data.
#
# On the instance, from an updated project folder:
#     sudo bash deployment/deploy.sh
set -euo pipefail

APP_DIR=/opt/quickbite
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $EUID -ne 0 ]]; then
  echo "Please run with sudo." >&2
  exit 1
fi

rsync -a \
  --exclude instance --exclude .env --exclude __pycache__ --exclude venv --exclude .git \
  "$SRC_DIR"/ "$APP_DIR"/
chown -R quickbite:quickbite "$APP_DIR"

"$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"
install -m 644 "$APP_DIR/deployment/quickbite.service" /etc/systemd/system/quickbite.service
install -m 644 "$APP_DIR/deployment/nginx-quickbite.conf" /etc/nginx/conf.d/quickbite.conf
nginx -t
systemctl daemon-reload
systemctl restart quickbite
systemctl reload nginx
echo "Deployed. Check: curl -s http://127.0.0.1/healthz"
