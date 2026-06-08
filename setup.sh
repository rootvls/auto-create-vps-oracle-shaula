#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$HOME/oracle-auto-create-adapted}"
SERVICE_NAME="oracle-auto-create-adapted.service"
USER_SYSTEMD_DIR="$HOME/.config/systemd/user"
VENV_DIR="${VENV_DIR:-$PROJECT_DIR/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$PROJECT_DIR"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "python3 not found"
  exit 1
fi

mkdir -p "$USER_SYSTEMD_DIR"

if [ ! -d "$VENV_DIR" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f oracle_auto_create.env ]; then
  cp oracle_auto_create.env.example oracle_auto_create.env
  echo "Created oracle_auto_create.env from example. Fill it before starting the service."
fi

cp oracle-auto-create.service "$USER_SYSTEMD_DIR/$SERVICE_NAME"
systemctl --user daemon-reload
systemctl --user enable "$SERVICE_NAME"

echo "Setup complete."
echo "Next: edit $PROJECT_DIR/oracle_auto_create.env"
echo "Then run: systemctl --user restart $SERVICE_NAME"
echo "Check: systemctl --user status $SERVICE_NAME"
