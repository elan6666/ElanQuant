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
SECONDARY_DEVICE=${SECONDARY_DEVICE:-cuda:1}

if [[ -e "$RESULTS_ROOT" ]]; then
  echo "immutable Plan011 results root already exists" >&2
  exit 73
fi
mkdir -p "$RESULTS_ROOT/signals" "$RESULTS_ROOT/backtests"

variants=(historical_top3 official_top50)
run_cell() {
  local cell=$1
  local device=$2
  "$PYTHON_BIN" "$ELANQUANT_ROOT/source/scripts/server/run_official_split_signals_v3.py" \
    --root "$ELANQUANT_ROOT" \
    --upstream "$UPSTREAM_ROOT" \
    --analysis-lock "$ANALYSIS_LOCK" \
    --matrix "$MATRIX_RECEIPT" \
    --dataset-manifest "$DATASET_MANIFEST" \
    --dataset-admission "$DATASET_ADMISSION" \
    --trade-calendar "$TRADE_CALENDAR" \
    --model-cell "$cell" \
    --device "$device" \
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
}

# Keep one process per GPU while overlapping the two independent model-size
# queues. Each cell still writes to its own immutable directory and each GPU
# runs only one inference process at a time.
(
  run_cell base-official-ft "$DEVICE"
  run_cell small-official-ft "$DEVICE"
) &
primary_pid=$!
(
  run_cell base-zero-shot "$SECONDARY_DEVICE"
  run_cell small-zero-shot "$SECONDARY_DEVICE"
) &
secondary_pid=$!

status=0
wait "$primary_pid" || status=$?
wait "$secondary_pid" || status=$?
exit "$status"
