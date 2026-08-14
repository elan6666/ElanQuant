#!/usr/bin/env bash
set -euo pipefail

ELANQUANT_ROOT=${ELANQUANT_ROOT:?}
PYTHON_BIN=${PYTHON_BIN:?}
UPSTREAM_ROOT=${UPSTREAM_ROOT:?}
QLIB_SITE_PACKAGES=${QLIB_SITE_PACKAGES:?}
ANALYSIS_LOCK=${ANALYSIS_LOCK:?}
MATRIX_RECEIPT=${MATRIX_RECEIPT:?}
DATASET_MANIFEST=${DATASET_MANIFEST:?}
DATASET_ADMISSION=${DATASET_ADMISSION:?}
TRADE_CALENDAR=${TRADE_CALENDAR:?}
RESULTS_ROOT=${RESULTS_ROOT:?}
DEVICE=${DEVICE:-cuda:0}

if [[ -e "$RESULTS_ROOT" ]]; then
  echo "immutable Plan011 results root already exists" >&2
  exit 73
fi
mkdir -p "$RESULTS_ROOT/signals" "$RESULTS_ROOT/backtests"

cells=(base-official-ft base-zero-shot small-official-ft small-zero-shot)
variants=(historical_top3 official_top50)
for cell in "${cells[@]}"; do
  "$PYTHON_BIN" "$ELANQUANT_ROOT/source/scripts/server/run_official_split_signals_v3.py" \
    --root "$ELANQUANT_ROOT" \
    --upstream "$UPSTREAM_ROOT" \
    --analysis-lock "$ANALYSIS_LOCK" \
    --matrix "$MATRIX_RECEIPT" \
    --dataset-manifest "$DATASET_MANIFEST" \
    --dataset-admission "$DATASET_ADMISSION" \
    --trade-calendar "$TRADE_CALENDAR" \
    --model-cell "$cell" \
    --device "$DEVICE" \
    --out-dir "$RESULTS_ROOT/signals/$cell"
  for variant in "${variants[@]}"; do
    "$PYTHON_BIN" "$ELANQUANT_ROOT/source/scripts/server/run_official_split_backtest_v3.py" \
      --root "$ELANQUANT_ROOT" \
      --analysis-lock "$ANALYSIS_LOCK" \
      --model-cell "$cell" \
      --strategy-variant "$variant" \
      --signal-receipt "$RESULTS_ROOT/signals/$cell/signal-receipt.json" \
      --qlib-site-packages "$QLIB_SITE_PACKAGES" \
      --out-dir "$RESULTS_ROOT/backtests/$cell/$variant"
  done
done
