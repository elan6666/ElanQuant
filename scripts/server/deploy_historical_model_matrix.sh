#!/usr/bin/env bash
set -euo pipefail

ROOT=${ELANQUANT_ROOT:-/data/yilangliu/a_share_research/elanquant}
SOURCE=${ELANQUANT_SOURCE:-$ROOT/source}
APP_PYTHON=${ELANQUANT_APP_PYTHON:-$ROOT/app-venv/bin/python}
CATALOG=$ROOT/releases/historical-backtest-catalog-v6.json
export PYTHONPATH="$SOURCE/backend/src:$ROOT/research-deps${PYTHONPATH:+:$PYTHONPATH}"

cd "$SOURCE"
[[ -f "$CATALOG" ]] || { echo "sealed matrix catalog is absent" >&2; exit 1; }

"$APP_PYTHON" - <<'PY'
import json
from pathlib import Path
from elanquant.contracts.historical_matrix import validate_catalog

path = Path("/data/yilangliu/a_share_research/elanquant/releases/historical-backtest-catalog-v6.json")
catalog = validate_catalog(json.loads(path.read_text(encoding="utf-8")))
assert len(catalog["entries"]) == 24
print("matrix catalog contract PASS")
PY

"$APP_PYTHON" -m pytest -q
"$ROOT/app-venv/bin/ruff" check backend/src scripts/server tests
"$ROOT/app-venv/bin/pyright" \
  --pythonpath "$APP_PYTHON" \
  backend/src scripts/server
"$APP_PYTHON" -m compileall -q backend/src scripts/server tests
npm --prefix frontend test -- --run
npm --prefix frontend run lint
npm --prefix frontend run build

install -m 0600 deploy/systemd/elanquant-api.service \
  "$HOME/.config/systemd/user/elanquant-api.service"
install -m 0600 deploy/systemd/elanquant-worker.service \
  "$HOME/.config/systemd/user/elanquant-worker.service"
systemctl --user daemon-reload
systemctl --user restart elanquant-api.service elanquant-worker.service

for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8765/api/v1/health >/dev/null; then
    break
  fi
  sleep 1
done
curl -fsS http://127.0.0.1:8765/api/v1/research/backtests | "$APP_PYTHON" -c \
  'import json,sys; p=json.load(sys.stdin); assert p["available"] and len(p["backtests"]) == 24; print("live matrix API PASS")'

echo "six-model historical matrix deployment PASS"
