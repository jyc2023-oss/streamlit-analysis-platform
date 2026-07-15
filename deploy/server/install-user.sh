#!/usr/bin/env bash
set -Eeuo pipefail

ARCHIVE_PATH="${1:-$HOME/streamlit-analysis-platform.tar}"
APP_ROOT="${APP_ROOT:-$HOME/apps/streamlit-analysis-platform}"
STATE_ROOT="${STATE_ROOT:-$HOME/.local/share/streamlit-analysis-platform}"
DATA_ROOT="${DATA_ROOT:-/srv/acquisition/raw}"
SERVICE_PORT="${SERVICE_PORT:-8501}"
SERVICE_HOST="${SERVICE_HOST:-127.0.0.1}"
MICROMAMBA="${MICROMAMBA:-$HOME/.local/bin/micromamba}"
MAMBA_ROOT_PREFIX="${MAMBA_ROOT_PREFIX:-$HOME/.local/share/mamba}"
ENV_NAME="streamlit-analysis"
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"

if [[ ! -r "$ARCHIVE_PATH" ]]; then
  echo "Deployment archive is not readable: $ARCHIVE_PATH" >&2
  exit 1
fi
if [[ ! -d "$DATA_ROOT" || ! -r "$DATA_ROOT" || ! -x "$DATA_ROOT" ]]; then
  echo "Data directory is not readable: $DATA_ROOT" >&2
  exit 1
fi

mkdir -p "$HOME/apps" "$STATE_ROOT" "$HOME/.local/bin" "$HOME/.config/systemd/user"

NEW_ROOT="${APP_ROOT}.new"
PREVIOUS_ROOT="${APP_ROOT}.previous"
rm -rf "$NEW_ROOT"
mkdir -p "$NEW_ROOT"
tar -xf "$ARCHIVE_PATH" -C "$NEW_ROOT"
if [[ -d "$APP_ROOT" ]]; then
  rm -rf "$PREVIOUS_ROOT"
  mv "$APP_ROOT" "$PREVIOUS_ROOT"
fi
mv "$NEW_ROOT" "$APP_ROOT"

if [[ ! -x "$MICROMAMBA" ]]; then
  TEMP_DIR="$(mktemp -d)"
  trap 'rm -rf "$TEMP_DIR"' EXIT
  curl -fsSL --retry 3 \
    https://micro.mamba.pm/api/micromamba/linux-64/latest \
    | tar -xj -C "$TEMP_DIR" bin/micromamba
  install -m 0755 "$TEMP_DIR/bin/micromamba" "$MICROMAMBA"
fi

export MAMBA_ROOT_PREFIX
export PIP_INDEX_URL
if ! "$MICROMAMBA" env list | awk '{print $1}' | grep -Fxq "$ENV_NAME"; then
  "$MICROMAMBA" create -y -n "$ENV_NAME" -c conda-forge python=3.12 pip
fi
"$MICROMAMBA" run -n "$ENV_NAME" python -m pip install --upgrade pip
"$MICROMAMBA" run -n "$ENV_NAME" python -m pip install -r "$APP_ROOT/requirements.txt"

cat > "$APP_ROOT/.env" <<EOF
APP_NAME=服务器数据分析平台
APP_ENV=production
APP_DATA_DIR=$STATE_ROOT
DATA_ROOTS=$DATA_ROOT
RESULT_RETENTION_DAYS=30
MAX_SCAN_FILES=100000
MAX_PREVIEW_POINTS=5000
MAX_ANALYSIS_SAMPLES=5000000
SESSION_IDLE_MINUTES=120
EOF
chmod 0600 "$APP_ROOT/.env"

UNIT_PATH="$HOME/.config/systemd/user/streamlit-analysis.service"
cat > "$UNIT_PATH" <<EOF
[Unit]
Description=Streamlit Data Analysis Platform
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$APP_ROOT
EnvironmentFile=$APP_ROOT/.env
Environment=MPLBACKEND=Agg
Environment=MAMBA_ROOT_PREFIX=$MAMBA_ROOT_PREFIX
ExecStart=$MICROMAMBA run -n $ENV_NAME python -m streamlit run app.py --server.address=$SERVICE_HOST --server.port=$SERVICE_PORT --server.headless=true --browser.gatherUsageStats=false
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
KillMode=mixed
UMask=0077

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable streamlit-analysis.service
systemctl --user restart streamlit-analysis.service

HEALTH_HOST="$SERVICE_HOST"
if [[ "$HEALTH_HOST" == "0.0.0.0" || "$HEALTH_HOST" == "::" ]]; then
  HEALTH_HOST="127.0.0.1"
fi
for _ in {1..30}; do
  if curl -fsS "http://$HEALTH_HOST:$SERVICE_PORT/_stcore/health" >/dev/null; then
    break
  fi
  sleep 1
done
curl -fsS "http://$HEALTH_HOST:$SERVICE_PORT/_stcore/health"
printf '\nAPP_ROOT=%s\nSTATE_ROOT=%s\nDATA_ROOT=%s\nHOST=%s\nPORT=%s\n' \
  "$APP_ROOT" "$STATE_ROOT" "$DATA_ROOT" "$SERVICE_HOST" "$SERVICE_PORT"
systemctl --user --no-pager --full status streamlit-analysis.service | head -n 20
