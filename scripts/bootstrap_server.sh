#!/usr/bin/env bash
set -euo pipefail

ROOT=${ELANQUANT_ROOT:-$HOME/.local/share/elanquant}
SOURCE=${ELANQUANT_SOURCE:-$ROOT/source}
APP_VENV=${ELANQUANT_APP_VENV:-$ROOT/app-venv}
PROFILE=${ELANQUANT_EXECUTION_PROFILE:-remote-linux-nvidia}
MODEL_RELEASE=${ELANQUANT_MODEL_RELEASE:-small}
DEVICE=${ELANQUANT_EXECUTION_DEVICE:-cuda}
STATE_ROOT=${ELANQUANT_STATE_ROOT:-$ROOT}

if [[ ! -d "$SOURCE/backend" || ! -f "$SOURCE/pyproject.toml" ]]; then
  echo "ElanQuant source is incomplete at $SOURCE" >&2
  exit 64
fi

python3 -m venv "$APP_VENV"
"$APP_VENV/bin/python" -m pip install --upgrade pip
"$APP_VENV/bin/python" -m pip install "$SOURCE[dev]"

cd "$SOURCE"
"$APP_VENV/bin/python" -m pytest -q
"$APP_VENV/bin/ruff" check backend/src scripts tests
"$APP_VENV/bin/pyright" --pythonpath "$APP_VENV/bin/python" backend/src scripts/research
"$APP_VENV/bin/python" -m compileall -q backend/src scripts tests

cd "$SOURCE/frontend"
if command -v npm >/dev/null 2>&1; then
  npm ci
  npm test
  npm run lint
  npm run build
elif [[ -f "$SOURCE/frontend/dist/index.html" ]]; then
  echo "npm is unavailable; using the prebuilt, locally verified frontend dist"
else
  echo "npm is unavailable and frontend/dist is missing" >&2
  exit 69
fi

install -d -m 700 "$ROOT/artifacts/runs" "$ROOT/artifacts/online-snapshots" "$ROOT/config"
install -d -m 700 "$HOME/.config/systemd/user"
ENV_FILE="$ROOT/config/$PROFILE.env"
cat >"$ENV_FILE" <<EOF
ELANQUANT_CONFIG=$SOURCE/configs/app.yaml
ELANQUANT_DB_PATH=$ROOT/artifacts/elanquant.sqlite3
ELANQUANT_ARTIFACT_ROOT=$ROOT/artifacts/runs
ELANQUANT_FRONTEND_DIST=$SOURCE/frontend/dist
ELANQUANT_EXECUTION_PROFILES_ROOT=$SOURCE/configs/execution
ELANQUANT_EXECUTION_PROFILE=$PROFILE
ELANQUANT_MODEL_RELEASE=$MODEL_RELEASE
ELANQUANT_EXECUTION_DEVICE=$DEVICE
ELANQUANT_INFERENCE_BATCH_SIZE=50
ELANQUANT_PIPELINE_MODE=real
ELANQUANT_RESEARCH_PYTHON=${ELANQUANT_RESEARCH_PYTHON:-$APP_VENV/bin/python}
ELANQUANT_RESEARCH_DEPS=${ELANQUANT_RESEARCH_DEPS:-$ROOT/research-deps}
ELANQUANT_PROXY_CLIENT=${ELANQUANT_PROXY_CLIENT:-$ROOT/provider/get_pro.py}
ELANQUANT_UPSTREAM_ROOT=${ELANQUANT_UPSTREAM_ROOT:-$ROOT/upstream/Kronos}
ELANQUANT_MATRIX_RECEIPT=${ELANQUANT_MATRIX_RECEIPT:-$ROOT/releases/current/training-matrix.json}
ELANQUANT_EVALUATION_RECEIPT=${ELANQUANT_EVALUATION_RECEIPT:-$ROOT/releases/current/formal-evaluation.json}
ELANQUANT_RESEARCH_CATALOG=${ELANQUANT_RESEARCH_CATALOG:-$ROOT/releases/research-catalog.json}
ELANQUANT_HISTORICAL_BACKTEST_CATALOG=${ELANQUANT_HISTORICAL_BACKTEST_CATALOG:-$ROOT/releases/historical-backtest-catalog.json}
EOF
chmod 600 "$ENV_FILE"

render_unit() {
  local name=$1
  sed \
    -e "s|@ELANQUANT_EXECUTION_PROFILE@|$PROFILE|g" \
    -e "s|@ELANQUANT_ROOT@|$SOURCE|g" \
    -e "s|@ELANQUANT_ENV_FILE@|$ENV_FILE|g" \
    -e "s|@ELANQUANT_APP_PYTHON@|$APP_VENV/bin/python|g" \
    -e "s|@ELANQUANT_STATE_ROOT@|$STATE_ROOT|g" \
    "$SOURCE/deploy/systemd/$name.service.in" \
    >"$HOME/.config/systemd/user/$name.service"
  chmod 600 "$HOME/.config/systemd/user/$name.service"
}

render_unit elanquant-api
render_unit elanquant-worker
systemctl --user daemon-reload

echo "Bootstrap complete. Enable services only after sealed matrix/evaluation receipts exist."
