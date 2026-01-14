#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

SYSTEMD_CHOICE="ask"
DISCORD_TOKEN=""
SERVICE_USER_OVERRIDE=""

for arg in "$@"; do
  case "$arg" in
    --systemd)
      SYSTEMD_CHOICE="yes"
      ;;
    --no-systemd)
      SYSTEMD_CHOICE="no"
      ;;
    --discord-token=*)
      DISCORD_TOKEN="${arg#*=}"
      ;;
    --service-user=*)
      SERVICE_USER_OVERRIDE="${arg#*=}"
      ;;
    *)
      echo "Unknown argument: $arg"
      echo "Usage: $0 [--systemd|--no-systemd] [--discord-token=TOKEN] [--service-user=USER]"
      exit 1
      ;;
  esac
done

if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
  IS_ROOT=1
else
  IS_ROOT=0
fi

if [[ "$SYSTEMD_CHOICE" == "ask" ]]; then
  if [[ "$IS_ROOT" -eq 1 ]]; then
    read -r -p "Create and enable a systemd service? [y/N]: " reply
    case "$reply" in
      y|Y|yes|YES)
        SYSTEMD_CHOICE="yes"
        ;;
      *)
        SYSTEMD_CHOICE="no"
        ;;
    esac
  else
    SYSTEMD_CHOICE="no"
  fi
fi

if [[ "$SYSTEMD_CHOICE" == "yes" && "$IS_ROOT" -ne 1 ]]; then
  echo "Systemd setup requires root. Re-run with sudo or use --no-systemd."
  exit 1
fi

CURRENT_USER="$(logname 2>/dev/null || id -un)"

SERVICE_USER="$CURRENT_USER"
CREATE_USER="no"
if [[ "$SYSTEMD_CHOICE" == "yes" ]]; then
  if [[ -n "$SERVICE_USER_OVERRIDE" ]]; then
    SERVICE_USER="$SERVICE_USER_OVERRIDE"
  else
    read -r -p "Create/use a dedicated service user? [y/N]: " reply
    case "$reply" in
      y|Y|yes|YES)
        read -r -p "Service user name [jukebox]: " SERVICE_USER
        SERVICE_USER="${SERVICE_USER:-jukebox}"
        ;;
      *)
        SERVICE_USER="$CURRENT_USER"
        ;;
    esac
  fi

  if id -u "$SERVICE_USER" >/dev/null 2>&1; then
    CREATE_USER="no"
  elif [[ "$SERVICE_USER" == "$CURRENT_USER" ]]; then
    CREATE_USER="no"
  else
    CREATE_USER="yes"
  fi
elif [[ -n "$SERVICE_USER_OVERRIDE" ]]; then
  echo "Note: --service-user is ignored because systemd is disabled."
fi

if [[ -z "$DISCORD_TOKEN" ]]; then
  while true; do
    read -r -s -p "Enter Discord bot token: " DISCORD_TOKEN
    echo
    if [[ -n "$DISCORD_TOKEN" ]]; then
      break
    fi
    echo "Token cannot be empty."
  done
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3.10+ is required but $PYTHON_BIN was not found."
  exit 1
fi

"$PYTHON_BIN" - <<'PY'
import sys

if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10+ is required.")
PY

cd "$REPO_DIR"

if [[ ! -d "$REPO_DIR/venv" ]]; then
  "$PYTHON_BIN" -m venv "$REPO_DIR/venv"
fi

if [[ ! -x "$REPO_DIR/venv/bin/pip" ]]; then
  "$REPO_DIR/venv/bin/python" -m ensurepip --upgrade
fi

"$REPO_DIR/venv/bin/python" -m pip install --upgrade pip
"$REPO_DIR/venv/bin/python" -m pip install -r "$REPO_DIR/requirements.txt"

ENV_FILE="$REPO_DIR/.env"
printf "DISCORD_TOKEN=%s\n" "$DISCORD_TOKEN" > "$ENV_FILE"
chmod 600 "$ENV_FILE"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "Warning: ffmpeg not found. Install it before running the bot."
fi

if [[ "$SYSTEMD_CHOICE" == "yes" ]]; then
  SERVICE_NAME="jukebox"
  SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
  if [[ "$CREATE_USER" == "yes" ]]; then
    NOLOGIN_SHELL="$(command -v nologin || echo /bin/false)"
    useradd --system --create-home --shell "$NOLOGIN_SHELL" "$SERVICE_USER"
    chown -R "$SERVICE_USER:$SERVICE_USER" "$REPO_DIR"
  fi

  REPO_OWNER="$(stat -c %U "$REPO_DIR" 2>/dev/null || echo "")"
  if [[ -n "$REPO_OWNER" && "$REPO_OWNER" != "$SERVICE_USER" ]]; then
    echo "Note: ensure '$SERVICE_USER' can read $REPO_DIR if the service fails to start."
  fi

  cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=Jukebox Discord bot
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$REPO_DIR
EnvironmentFile=$REPO_DIR/.env
ExecStart=$REPO_DIR/venv/bin/python -m jukebox.main
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable --now "$SERVICE_NAME"
  echo "Systemd service '${SERVICE_NAME}' is enabled and running."
fi

echo "Install complete."
