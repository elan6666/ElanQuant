#!/usr/bin/env bash
set -euo pipefail

ROOT=${ELANQUANT_ROOT:-/data/yilangliu/a_share_research/elanquant}
SOURCE=${ELANQUANT_SOURCE:-$ROOT/source}
APP_VENV=${ELANQUANT_APP_VENV:-$ROOT/app-venv}

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

install -d -m 700 "$ROOT/artifacts/runs" "$ROOT/artifacts/online-snapshots"
install -d -m 700 "$HOME/.config/systemd/user"
install -m 600 "$SOURCE/deploy/systemd/elanquant-api.service" \
  "$HOME/.config/systemd/user/elanquant-api.service"
install -m 600 "$SOURCE/deploy/systemd/elanquant-worker.service" \
  "$HOME/.config/systemd/user/elanquant-worker.service"
systemctl --user daemon-reload

echo "Bootstrap complete. Enable services only after sealed matrix/evaluation receipts exist."
