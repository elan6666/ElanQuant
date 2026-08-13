#!/usr/bin/env bash
set -euo pipefail

ROOT=${ELANQUANT_ROOT:-/data/yilangliu/a_share_research/elanquant}
SOURCE=${ELANQUANT_SOURCE:-$ROOT/source}
RUN=${ELANQUANT_TOP3_RUN:-$ROOT/runs/backtests/historical-top3-variant-v2-20260813}
VALIDATION_RUN=${ELANQUANT_VALIDATION_RUN:-$ROOT/runs/backtests/official-demo-method-v1-20260813}
OPENED_RUN=${ELANQUANT_OPENED_RUN:-$ROOT/runs/backtests/official-demo-method-corrected-opened-2026-v1-20260813-r5}
RESEARCH_PYTHON=${ELANQUANT_RESEARCH_PYTHON:-/data/yilangliu/a_share_research/seven_model_research/.venv/bin/python}
APP_PYTHON=${ELANQUANT_APP_PYTHON:-$ROOT/app-venv/bin/python}
QLIB_SITE=${ELANQUANT_QLIB_SITE:-/data/yilangliu/a_share_research/alphagen-venv/lib/python3.12/site-packages}
export PYTHONPATH="$SOURCE/backend/src:$ROOT/research-deps${PYTHONPATH:+:$PYTHONPATH}"

MATRIX=$ROOT/releases/current/training-matrix.json
LOCK=$RUN/variant-lock-receipt.json
VALIDATION_RESULT=$RUN/validation-2025/result
OPENED_RESULT=$RUN/test-viewed-2026/result
VALIDATION_TOP50_HOLDINGS=$RUN/validation-2025/official-top50-holdings
OPENED_TOP50_HOLDINGS=$RUN/test-viewed-2026/official-top50-holdings
CATALOG=$ROOT/releases/historical-backtest-catalog-v5.json
BEFORE=$RUN/paper-boundary-before.json
AFTER=$RUN/paper-boundary-after.json
CURRENT_LINK=$ROOT/releases/current
CURRENT_TARGET=$(readlink "$CURRENT_LINK")
VALIDATION_TOP50=$VALIDATION_RUN/result/backtest-receipt.json
OPENED_TOP50=$OPENED_RUN/result/backtest-receipt.json

cd "$SOURCE"
[[ ! -e "$RUN" && ! -e "$CATALOG" ]] || {
  echo "Top3 run or v3 catalog output already exists" >&2
  exit 1
}
for input in \
  "$MATRIX" \
  "$VALIDATION_TOP50" \
  "$OPENED_TOP50" \
  "$VALIDATION_RUN/signals/signal-receipt.json" \
  "$VALIDATION_RUN/qlib-provider-r4/provider-receipt.json" \
  "$OPENED_RUN/signals/signal-receipt.json" \
  "$OPENED_RUN/qlib-provider/provider-receipt.json"; do
  [[ -f "$input" ]] || { echo "sealed input absent: $input" >&2; exit 1; }
done
mkdir -p "$RUN"

"$APP_PYTHON" scripts/server/audit_paper_boundary.py \
  --database "$ROOT/artifacts/elanquant.sqlite3" \
  --out "$BEFORE"

# This lock is created and validated before either result process starts. It
# binds the final runner and contract bytes, Qlib distribution, model matrix,
# and the exact signal/provider receipts for both splits.
"$RESEARCH_PYTHON" scripts/server/build_historical_top3_variant_lock.py \
  --root "$ROOT" \
  --runner "$SOURCE/scripts/server/run_historical_top3_variant.py" \
  --contract "$SOURCE/backend/src/elanquant/contracts/historical_variants.py" \
  --matrix "$MATRIX" \
  --qlib-site-packages "$QLIB_SITE" \
  --validation-signal-receipt "$VALIDATION_RUN/signals/signal-receipt.json" \
  --validation-provider-receipt "$VALIDATION_RUN/qlib-provider-r4/provider-receipt.json" \
  --opened-signal-receipt "$OPENED_RUN/signals/signal-receipt.json" \
  --opened-provider-receipt "$OPENED_RUN/qlib-provider/provider-receipt.json" \
  --out "$LOCK"

"$RESEARCH_PYTHON" scripts/server/run_historical_top3_variant.py \
  --root "$ROOT" \
  --variant-lock "$LOCK" \
  --split validation_2025 \
  --strategy-variant official_top50 \
  --backtest-receipt "$VALIDATION_TOP50" \
  --qlib-site-packages "$QLIB_SITE" \
  --out-dir "$VALIDATION_TOP50_HOLDINGS"

"$RESEARCH_PYTHON" scripts/server/run_historical_top3_variant.py \
  --root "$ROOT" \
  --variant-lock "$LOCK" \
  --split validation_2025 \
  --strategy-variant historical_top3 \
  --qlib-site-packages "$QLIB_SITE" \
  --out-dir "$VALIDATION_RESULT"
cp "$SOURCE/scripts/server/run_historical_top3_variant.py" "$VALIDATION_RESULT/backtest-source.py"

"$RESEARCH_PYTHON" scripts/server/run_historical_top3_variant.py \
  --root "$ROOT" \
  --variant-lock "$LOCK" \
  --split test_viewed_2026 \
  --strategy-variant official_top50 \
  --backtest-receipt "$OPENED_TOP50" \
  --qlib-site-packages "$QLIB_SITE" \
  --out-dir "$OPENED_TOP50_HOLDINGS"

"$RESEARCH_PYTHON" scripts/server/run_historical_top3_variant.py \
  --root "$ROOT" \
  --variant-lock "$LOCK" \
  --split test_viewed_2026 \
  --strategy-variant historical_top3 \
  --qlib-site-packages "$QLIB_SITE" \
  --out-dir "$OPENED_RESULT"
cp "$SOURCE/scripts/server/run_historical_top3_variant.py" "$OPENED_RESULT/backtest-source.py"

"$APP_PYTHON" scripts/server/build_historical_backtest_catalog_v3.py \
  --root "$ROOT" \
  --backtest-receipt "$VALIDATION_TOP50" \
  --backtest-receipt "$VALIDATION_RESULT/backtest-receipt.json" \
  --backtest-receipt "$OPENED_TOP50" \
  --backtest-receipt "$OPENED_RESULT/backtest-receipt.json" \
  --holdings-receipt "$VALIDATION_TOP50_HOLDINGS/holdings-receipt.json" \
  --holdings-receipt "$VALIDATION_RESULT/holdings-receipt.json" \
  --holdings-receipt "$OPENED_TOP50_HOLDINGS/holdings-receipt.json" \
  --holdings-receipt "$OPENED_RESULT/holdings-receipt.json" \
  --out "$CATALOG"

"$APP_PYTHON" scripts/server/audit_paper_boundary.py \
  --database "$ROOT/artifacts/elanquant.sqlite3" \
  --compare "$BEFORE" \
  --out "$AFTER"

find "$RUN" -type f -exec chmod 0440 {} +
find "$RUN" -type d -exec chmod 0550 {} +
chmod 0440 "$CATALOG"

"$APP_PYTHON" scripts/server/audit_historical_top3_variant.py \
  --root "$ROOT" \
  --catalog "$CATALOG" \
  --variant-lock "$LOCK" \
  --paper-before "$BEFORE" \
  --paper-after "$AFTER" \
  --current-link "$CURRENT_LINK" \
  --expected-current-target "$CURRENT_TARGET"

echo "sealed Top3 historical sensitivity variants PASS"
