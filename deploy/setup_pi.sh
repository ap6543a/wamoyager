#!/usr/bin/env bash
# setup_pi.sh — Bootstrap wamoyager on a fresh Raspberry Pi OS installation.
# Run as the 'pi' user (not root).

set -euo pipefail

REPO_DIR="$HOME/wamoyager"
VENV_DIR="$REPO_DIR/venv"
SERVICE_NAME="wamoyager"

echo "==> Updating apt packages..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv git sqlite3

echo "==> Creating Python virtual environment at $VENV_DIR..."
python3 -m venv "$VENV_DIR"

echo "==> Installing Python dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$REPO_DIR/requirements.txt"

echo "==> Copying .env.example to .env (if .env not already present)..."
if [ ! -f "$REPO_DIR/.env" ]; then
    cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
    echo "   IMPORTANT: Edit $REPO_DIR/.env and fill in your real API keys before starting."
fi

echo "==> Initializing database..."
DATABASE_PATH="$REPO_DIR/wamoyager.db" "$VENV_DIR/bin/python" "$REPO_DIR/scripts/init_db.py"

echo "==> Installing systemd service..."
sudo cp "$REPO_DIR/deploy/systemd/$SERVICE_NAME.service" "/etc/systemd/system/$SERVICE_NAME.service"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"

echo ""
echo "Setup complete!"
echo "Edit $REPO_DIR/.env with your WMATA_API_KEY and Twilio credentials, then run:"
echo "  sudo systemctl start $SERVICE_NAME"
echo "  sudo journalctl -u $SERVICE_NAME -f"
