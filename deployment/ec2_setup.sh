#!/usr/bin/env bash
# Install and start QuickBite on an Amazon Linux 2023 EC2 instance.
#
# Run ON the instance, from the project folder:
#     sudo bash deployment/ec2_setup.sh
#
# It is safe to run again. It keeps your existing /etc/quickbite/quickbite.env.
set -euo pipefail

APP_DIR=/opt/quickbite
ENV_DIR=/etc/quickbite
ENV_FILE="$ENV_DIR/quickbite.env"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $EUID -ne 0 ]]; then
  echo "Please run with sudo: sudo bash deployment/ec2_setup.sh" >&2
  exit 1
fi

echo "==> Installing system packages"
dnf install -y python3 python3-pip nginx rsync

echo "==> Creating service user"
id -u quickbite &>/dev/null || useradd --system --home "$APP_DIR" --shell /sbin/nologin quickbite

echo "==> Copying application to $APP_DIR"
mkdir -p "$APP_DIR" "$ENV_DIR"
if [[ "$SRC_DIR" != "$APP_DIR" ]]; then
  rsync -a --delete \
    --exclude instance --exclude .env --exclude __pycache__ --exclude venv --exclude .git \
    "$SRC_DIR"/ "$APP_DIR"/
fi

echo "==> Creating Python virtual environment and installing dependencies"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

echo "==> Preparing environment file"
if [[ ! -f "$ENV_FILE" ]]; then
  install -m 640 "$APP_DIR/.env.example" "$ENV_FILE"
  sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))')|" "$ENV_FILE"
  sed -i "s|^APP_MODE=.*|APP_MODE=aws|" "$ENV_FILE"
  echo "    Created $ENV_FILE. Add STAFF_PASSWORD_HASH before students and staff use the app."
fi
chown root:quickbite "$ENV_FILE"
chmod 640 "$ENV_FILE"
chown -R quickbite:quickbite "$APP_DIR"

echo "==> Installing systemd service and nginx configuration"
install -m 644 "$APP_DIR/deployment/quickbite.service" /etc/systemd/system/quickbite.service
install -m 644 "$APP_DIR/deployment/nginx.conf" /etc/nginx/nginx.conf
install -m 644 "$APP_DIR/deployment/nginx-quickbite.conf" /etc/nginx/conf.d/quickbite.conf
nginx -t

echo "==> Starting services"
systemctl daemon-reload
systemctl enable --now quickbite
systemctl enable --now nginx
systemctl restart quickbite
systemctl restart nginx

echo
echo "QuickBite is installed."
echo "  Check the app:    systemctl status quickbite --no-pager"
echo "  View logs:        journalctl -u quickbite -n 50 --no-pager"
echo "  Test locally:     curl -s http://127.0.0.1/healthz"
echo "  Next step:        sudo nano $ENV_FILE   (set STAFF_PASSWORD_HASH, then: sudo systemctl restart quickbite)"
