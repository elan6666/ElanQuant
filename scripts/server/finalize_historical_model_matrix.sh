#!/usr/bin/env bash
set -euo pipefail

ROOT=${ELANQUANT_ROOT:-/data/yilangliu/a_share_research/elanquant}
SOURCE=${ELANQUANT_SOURCE:-$ROOT/source}
RUN=${ELANQUANT_MATRIX_RUN:-$ROOT/runs/backtests/historical-six-model-matrix-v1-20260814}
RESEARCH_PYTHON=${ELANQUANT_RESEARCH_PYTHON:-/data/yilangliu/a_share_research/seven_model_research/.venv/bin/python}
APP_PYTHON=${ELANQUANT_APP_PYTHON:-$ROOT/app-venv/bin/python}
QLIB_SITE=${ELANQUANT_QLIB_SITE:-/data/yilangliu/a_share_research/alphagen-venv/lib/python3.12/site-packages}
export PYTHONPATH="$SOURCE/backend/src:$ROOT/research-deps${PYTHONPATH:+:$PYTHONPATH}"

SIGNALS=$RUN/signals
RESULTS=$RUN/results
LOCK=$RUN/matrix-lock-receipt.json
CATALOG=$ROOT/releases/historical-backtest-catalog-v6.json
BEFORE=$RUN/paper-boundary-before.json
AFTER=$RUN/paper-boundary-after.json
VALIDATION_PROVIDER=$ROOT/runs/backtests/official-demo-method-v1-20260813/qlib-provider-r4/provider-receipt.json
OPENED_PROVIDER=$ROOT/runs/backtests/official-demo-method-corrected-opened-2026-v1-20260813-r5/qlib-provider/provider-receipt.json
CURRENT_TARGET=$(readlink "$ROOT/releases/current")

cd "$SOURCE"
[[ ! -e "$LOCK" && ! -e "$RESULTS" && ! -e "$CATALOG" ]] || {
  echo "immutable matrix result, lock, or catalog already exists" >&2
  exit 1
}
for model in small-zero-shot small-official-ft small-strict-pit \
  base-zero-shot base-official-ft base-strict-pit; do
  for split in validation_2025 test_viewed_2026; do
    receipt="$SIGNALS/$model/$split/signal-receipt.json"
    [[ -f "$receipt" ]] || { echo "matrix signal absent: $receipt" >&2; exit 1; }
  done
done

"$APP_PYTHON" scripts/server/audit_paper_boundary.py \
  --database "$ROOT/artifacts/elanquant.sqlite3" \
  --out "$BEFORE"

"$RESEARCH_PYTHON" scripts/server/build_historical_matrix_lock.py \
  --root "$ROOT" \
  --signals-root "$SIGNALS" \
  --validation-provider-receipt "$VALIDATION_PROVIDER" \
  --opened-provider-receipt "$OPENED_PROVIDER" \
  --runner "$SOURCE/scripts/server/run_historical_model_matrix_backtest.py" \
  --contract "$SOURCE/backend/src/elanquant/contracts/historical_matrix.py" \
  --qlib-site-packages "$QLIB_SITE" \
  --out "$LOCK"

for model in small-zero-shot small-official-ft small-strict-pit \
  base-zero-shot base-official-ft base-strict-pit; do
  for split in validation_2025 test_viewed_2026; do
    for variant in official_top50 historical_top3; do
      "$RESEARCH_PYTHON" scripts/server/run_historical_model_matrix_backtest.py \
        --root "$ROOT" \
        --matrix-lock "$LOCK" \
        --model-cell "$model" \
        --split "$split" \
        --strategy-variant "$variant" \
        --qlib-site-packages "$QLIB_SITE" \
        --out-dir "$RESULTS/$model/$split/$variant"
    done
  done
done

"$APP_PYTHON" scripts/server/build_historical_model_matrix_catalog.py \
  --root "$ROOT" \
  --results-root "$RESULTS" \
  --out "$CATALOG"

"$APP_PYTHON" scripts/server/audit_paper_boundary.py \
  --database "$ROOT/artifacts/elanquant.sqlite3" \
  --compare "$BEFORE" \
  --out "$AFTER"

[[ "$(readlink "$ROOT/releases/current")" == "$CURRENT_TARGET" ]] || {
  echo "online release changed during historical matrix run" >&2
  exit 1
}
find "$RUN" -type f -exec chmod 0440 {} +
find "$RUN" -type d -exec chmod 0550 {} +
chmod 0440 "$CATALOG"

echo "sealed six-model historical matrix PASS"
