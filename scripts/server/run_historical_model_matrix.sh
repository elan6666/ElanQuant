#!/usr/bin/env bash
set -euo pipefail

ROOT=${ELANQUANT_ROOT:-/data/yilangliu/a_share_research/elanquant}
SOURCE=${ELANQUANT_SOURCE:-$ROOT/source}
RUN=${ELANQUANT_MATRIX_RUN:-$ROOT/runs/backtests/historical-six-model-matrix-v1-20260814}
MODEL_SIZE=${ELANQUANT_MODEL_SIZE_ONLY:?set ELANQUANT_MODEL_SIZE_ONLY=small or base}
DEVICE=${ELANQUANT_DEVICE:-cuda:0}
RESEARCH_PYTHON=${ELANQUANT_RESEARCH_PYTHON:-/data/yilangliu/a_share_research/seven_model_research/.venv/bin/python}
export PYTHONPATH="$SOURCE/backend/src:$ROOT/research-deps${PYTHONPATH:+:$PYTHONPATH}"

[[ "$MODEL_SIZE" == small || "$MODEL_SIZE" == base ]] || {
  echo "MODEL_SIZE must be small or base" >&2
  exit 1
}
MATRIX=$ROOT/runs/training/kronos-a-share-v2-20260813/matrix.json
[[ "$MODEL_SIZE" == base ]] && MATRIX=$ROOT/runs/training/kronos-base-a-share-v1-20260813/matrix.json
MANIFEST=$ROOT/data/processed/extended-v2/manifest.json
VALIDATION_DATA=$ROOT/data/processed/extended-v2/official/val_data.pkl
OPENED_DATA=$ROOT/data/processed/extended-v2/official/test_data.pkl
VALIDATION_REFERENCE=$ROOT/runs/backtests/official-demo-method-v1-20260813/signals/signal-receipt.json
OPENED_REFERENCE=$ROOT/runs/backtests/official-demo-method-corrected-opened-2026-v1-20260813-r5/signals/signal-receipt.json

cd "$SOURCE"
for input in "$MATRIX" "$MANIFEST" "$VALIDATION_DATA" "$OPENED_DATA" \
  "$VALIDATION_REFERENCE" "$OPENED_REFERENCE"; do
  [[ -f "$input" ]] || { echo "sealed input absent: $input" >&2; exit 1; }
done
mkdir -p "$RUN/signals"

for track in zero-shot official-ft strict-pit; do
  model="$MODEL_SIZE-$track"
  for split in validation_2025 test_viewed_2026; do
    out="$RUN/signals/$model/$split"
    [[ ! -e "$out" ]] || { echo "immutable signal output exists: $out" >&2; exit 1; }
    dataset=$VALIDATION_DATA
    reference=$VALIDATION_REFERENCE
    start=2025-01-01
    end=2025-12-31
    if [[ "$split" == test_viewed_2026 ]]; then
      dataset=$OPENED_DATA
      reference=$OPENED_REFERENCE
      start=2026-01-01
      end=2026-08-12
    fi
    "$RESEARCH_PYTHON" scripts/server/generate_official_demo_signals.py \
      --root "$ROOT" \
      --upstream "$ROOT/upstream/Kronos" \
      --matrix "$MATRIX" \
      --dataset-manifest "$MANIFEST" \
      --dataset "$dataset" \
      --out-dir "$out" \
      --model-cell "$model" \
      --reference-signal-receipt "$reference" \
      --evaluation-split "$split" \
      --start "$start" \
      --end "$end" \
      --device "$DEVICE"
  done
done

echo "$MODEL_SIZE historical model signals PASS"
