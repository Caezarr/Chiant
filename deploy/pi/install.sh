#!/usr/bin/env sh
set -eu

SOURCE_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
INSTALL_DIR="/opt/boring"
STATE_DIR="/var/lib/boring"
SERVICE_PATH="/etc/systemd/system/boring-box.service"
START_SERVICE=0
SKIP_SYNC=0
DRY_RUN="${DRY_RUN:-0}"

usage() {
  cat <<'EOF'
Usage: deploy/pi/install.sh [--source DIR] [--install-dir DIR] [--state-dir DIR] [--start]

Installe la Boring Parking Box sur Raspberry Pi OS.
Par defaut, prepare systemd mais ne demarre pas le service.

Options:
  --source DIR       Repo source a copier (defaut: repo courant)
  --install-dir DIR  Destination applicative (defaut: /opt/boring)
  --state-dir DIR    Etat persistant (defaut: /var/lib/boring)
  --start            Enable + start boring-box apres installation
  --skip-sync        Ne pas lancer uv sync --no-dev apres copie

Env:
  DRY_RUN=1          Affiche les actions sans les executer
EOF
}

run() {
  if [ "$DRY_RUN" = "1" ]; then
    printf '+ %s\n' "$*"
  else
    "$@"
  fi
}

render_service() {
  target="$1"
  if [ "$DRY_RUN" = "1" ]; then
    printf '+ render boring-box.service > %s (INSTALL_DIR=%s STATE_DIR=%s)\n' \
      "$target" "$INSTALL_DIR" "$STATE_DIR"
    return
  fi

  cat > "$target" <<EOF
[Unit]
Description=Boring Parking Box
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=/usr/bin/env uv run boring box-run
Restart=always
RestartSec=5
WatchdogSec=120
NotifyAccess=main
User=boring
Group=video
SupplementaryGroups=video gpio i2c netdev
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ReadWritePaths=$INSTALL_DIR $STATE_DIR

[Install]
WantedBy=multi-user.target
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --source)
      SOURCE_DIR="$2"
      shift 2
      ;;
    --install-dir)
      INSTALL_DIR="$2"
      shift 2
      ;;
    --state-dir)
      STATE_DIR="$2"
      shift 2
      ;;
    --start)
      START_SERVICE=1
      shift
      ;;
    --skip-sync)
      SKIP_SYNC=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ "$(id -u)" -ne 0 ] && [ "$DRY_RUN" != "1" ]; then
  echo "Run with sudo, or set DRY_RUN=1 for rehearsal." >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1 && [ "$DRY_RUN" != "1" ]; then
  echo "uv is required before install." >&2
  exit 1
fi

if id boring >/dev/null 2>&1; then
  echo "User boring already exists."
else
  run useradd --system --create-home --groups video,gpio,i2c,netdev boring
fi
run mkdir -p "$INSTALL_DIR" "$STATE_DIR"
run chown -R boring:boring "$INSTALL_DIR" "$STATE_DIR"

if command -v rsync >/dev/null 2>&1; then
  run rsync -a --delete \
    --exclude .git \
    --exclude .venv \
    --exclude datasets \
    --exclude runs \
    --exclude frames \
    "$SOURCE_DIR"/ "$INSTALL_DIR"/
elif [ "$DRY_RUN" = "1" ]; then
  run rsync -a --delete \
    --exclude .git \
    --exclude .venv \
    --exclude datasets \
    --exclude runs \
    --exclude frames \
    "$SOURCE_DIR"/ "$INSTALL_DIR"/
else
  run cp -R "$SOURCE_DIR"/. "$INSTALL_DIR"/
fi

if [ ! -f "$INSTALL_DIR/.env" ]; then
  run cp "$INSTALL_DIR/deploy/pi/box.env.example" "$INSTALL_DIR/.env"
fi

if [ ! -f "$INSTALL_DIR/deploy/pi/hardware-profile.json" ]; then
  run cp "$INSTALL_DIR/deploy/pi/hardware-profile.example.json" \
    "$INSTALL_DIR/deploy/pi/hardware-profile.json"
fi

run chmod 0755 "$INSTALL_DIR/deploy/pi/network-recover.example.sh"
run chown -R boring:boring "$INSTALL_DIR" "$STATE_DIR"

if [ "$SKIP_SYNC" = "0" ]; then
  run su -s /bin/sh boring -c "cd '$INSTALL_DIR' && uv sync --no-dev"
  run su -s /bin/sh boring -c "cd '$INSTALL_DIR' && uv run boring --help >/dev/null"
fi

render_service "$SERVICE_PATH"
run systemctl daemon-reload

if [ "$START_SERVICE" = "1" ]; then
  run systemctl enable boring-box
  run systemctl restart boring-box
else
  echo "Install complete. Edit $INSTALL_DIR/.env, then run:"
  echo "  cd $INSTALL_DIR && uv run boring box-doctor"
  echo "  sudo systemctl enable boring-box && sudo systemctl start boring-box"
fi
