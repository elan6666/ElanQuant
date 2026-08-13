#!/usr/bin/env bash
set -euo pipefail

ROOT=${ELANQUANT_ROOT:-/data/yilangliu/a_share_research/elanquant}
SOURCE=${ELANQUANT_SOURCE:-$ROOT/source}
RUN=${ELANQUANT_OFFICIAL_DEMO_RUN:-$ROOT/runs/backtests/official-demo-method-v1-20260813}
RESEARCH_PYTHON=${ELANQUANT_RESEARCH_PYTHON:-/data/yilangliu/a_share_research/seven_model_research/.venv/bin/python}
APP_PYTHON=${ELANQUANT_APP_PYTHON:-$ROOT/app-venv/bin/python}
QLIB_SITE=${ELANQUANT_QLIB_SITE:-/data/yilangliu/a_share_research/alphagen-venv/lib/python3.12/site-packages}
SIGNAL_SERVICE=${ELANQUANT_SIGNAL_SERVICE:-elanquant-generate-official-demo-signals-v1-20260813-r2.service}
SIGNAL_RECEIPT=$RUN/signals/signal-receipt.json
PROVIDER_RECEIPT=$RUN/qlib-provider-r4/provider-receipt.json
RESULT=$RUN/result
CATALOG=$ROOT/releases/historical-backtest-catalog.json
BEFORE=$RUN/paper-boundary-before.json
AFTER=$RUN/paper-boundary-after.json

for _ in $(seq 1 1440); do
  if [[ -f "$SIGNAL_RECEIPT" ]]; then
    break
  fi
  if systemctl --user is-failed --quiet "$SIGNAL_SERVICE"; then
    echo "signal service failed before publishing its receipt" >&2
    exit 1
  fi
  sleep 10
done

[[ -f "$SIGNAL_RECEIPT" ]] || { echo "signal receipt timeout" >&2; exit 1; }
[[ -f "$PROVIDER_RECEIPT" ]] || { echo "provider receipt is absent" >&2; exit 1; }
[[ ! -e "$RESULT" ]] || { echo "backtest result already exists" >&2; exit 1; }
[[ ! -e "$CATALOG" ]] || { echo "historical backtest catalog already exists" >&2; exit 1; }
[[ -f "$BEFORE" ]] || { echo "paper boundary baseline is absent" >&2; exit 1; }

SIGNAL_SOURCE=$RUN/signals/generator-source.py
if [[ ! -e "$SIGNAL_SOURCE" ]]; then
  cp "$SOURCE/scripts/server/generate_official_demo_signals.py" "$SIGNAL_SOURCE"
  chmod 400 "$SIGNAL_SOURCE"
fi
SIGNAL_SOURCE_SHA=$(sha256sum "$SIGNAL_SOURCE" | awk '{print $1}')
EXPECTED_SIGNAL_SOURCE_SHA=$("$APP_PYTHON" -c \
  'import json,sys; print(json.load(open(sys.argv[1]))["generator_code_sha256"])' \
  "$SIGNAL_RECEIPT")
[[ "$SIGNAL_SOURCE_SHA" == "$EXPECTED_SIGNAL_SOURCE_SHA" ]] || {
  echo "executed signal source does not match its receipt" >&2
  exit 1
}

cd "$SOURCE"
"$RESEARCH_PYTHON" scripts/server/run_official_demo_backtest.py \
  --root "$ROOT" \
  --signal-receipt "$SIGNAL_RECEIPT" \
  --provider-receipt "$PROVIDER_RECEIPT" \
  --qlib-site-packages "$QLIB_SITE" \
  --out-dir "$RESULT"

BACKTEST_SOURCE=$RESULT/backtest-source.py
cp "$SOURCE/scripts/server/run_official_demo_backtest.py" "$BACKTEST_SOURCE"
BACKTEST_SOURCE_SHA=$(sha256sum "$BACKTEST_SOURCE" | awk '{print $1}')
EXPECTED_BACKTEST_SOURCE_SHA=$("$APP_PYTHON" -c \
  'import json,sys; print(json.load(open(sys.argv[1]))["backtest_code_sha256"])' \
  "$RESULT/backtest-receipt.json")
[[ "$BACKTEST_SOURCE_SHA" == "$EXPECTED_BACKTEST_SOURCE_SHA" ]] || {
  echo "executed backtest source does not match its receipt" >&2
  exit 1
}
chmod 400 "$BACKTEST_SOURCE"

"$APP_PYTHON" scripts/server/build_official_demo_catalog.py \
  --root "$ROOT" \
  --backtest-receipt "$RESULT/backtest-receipt.json" \
  --out "$CATALOG"

"$APP_PYTHON" scripts/server/audit_paper_boundary.py \
  --database "$ROOT/artifacts/elanquant.sqlite3" \
  --compare "$BEFORE" \
  --out "$AFTER"

echo "official demo historical track PASS"
