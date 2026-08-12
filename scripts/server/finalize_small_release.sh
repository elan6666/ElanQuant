#!/usr/bin/env bash
set -euo pipefail

ELANQUANT_ROOT=${ELANQUANT_ROOT:?}
ELANQUANT_RUN_ID=${ELANQUANT_RUN_ID:?}
ELANQUANT_TRAINING_UNIT=${ELANQUANT_TRAINING_UNIT:?}
ELANQUANT_ONLINE_ROOT=${ELANQUANT_ONLINE_ROOT:?}
PYTHON_BIN=${PYTHON_BIN:?}
ELANQUANT_UPSTREAM_ROOT=${ELANQUANT_UPSTREAM_ROOT:?}

SOURCE=${ELANQUANT_SOURCE:-$ELANQUANT_ROOT/source}
TRAIN_ROOT=$ELANQUANT_ROOT/runs/training/$ELANQUANT_RUN_ID
EVAL_ROOT=$ELANQUANT_ROOT/runs/evaluation/$ELANQUANT_RUN_ID
MATRIX=$TRAIN_ROOT/matrix.json
SMOKE=$EVAL_ROOT/smoke-evaluation.json
FORMAL=$EVAL_ROOT/formal-evaluation.json

while systemctl --user is-active --quiet "$ELANQUANT_TRAINING_UNIT"; do
  sleep 10
done

terminals=(
  "$TRAIN_ROOT/official-tokenizer-small/terminal.json"
  "$TRAIN_ROOT/official-predictor-small/terminal.json"
  "$TRAIN_ROOT/strict-tokenizer-small/terminal.json"
  "$TRAIN_ROOT/strict-predictor-small/terminal.json"
)
for terminal in "${terminals[@]}"; do
  [[ -f "$terminal" ]] || { echo "missing terminal receipt: $terminal" >&2; exit 66; }
  "$PYTHON_BIN" - "$terminal" <<'PY'
import json, pathlib, sys
receipt = json.loads(pathlib.Path(sys.argv[1]).read_text())
raise SystemExit(0 if receipt.get("status") == "PASS" else 1)
PY
done

mkdir -p "$EVAL_ROOT"
cd "$SOURCE"
"$PYTHON_BIN" scripts/server/compile_training_matrix.py \
  --root "$ELANQUANT_ROOT" \
  --run-id "$ELANQUANT_RUN_ID" \
  --output "$MATRIX"

export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0}
"$PYTHON_BIN" scripts/server/evaluate_and_infer.py \
  --root "$ELANQUANT_ROOT" \
  --upstream "$ELANQUANT_UPSTREAM_ROOT" \
  --matrix-receipt "$MATRIX" \
  --online-root "$ELANQUANT_ONLINE_ROOT" \
  --smoke-evaluation-samples 600 \
  --batch-size 50 \
  --out "$SMOKE"

"$PYTHON_BIN" scripts/server/evaluate_and_infer.py \
  --root "$ELANQUANT_ROOT" \
  --upstream "$ELANQUANT_UPSTREAM_ROOT" \
  --matrix-receipt "$MATRIX" \
  --online-root "$ELANQUANT_ONLINE_ROOT" \
  --formal-sessions-per-month 5 \
  --batch-size 50 \
  --out "$FORMAL"

"$PYTHON_BIN" scripts/server/publish_release.py \
  --root "$ELANQUANT_ROOT" \
  --release-id "$ELANQUANT_RUN_ID" \
  --matrix "$MATRIX" \
  --evaluation "$FORMAL"

echo "Small release published: $ELANQUANT_RUN_ID"
