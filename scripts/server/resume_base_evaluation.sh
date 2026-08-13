#!/usr/bin/env bash
set -euo pipefail

ELANQUANT_ROOT=${ELANQUANT_ROOT:?}
ELANQUANT_RUN_ID=${ELANQUANT_RUN_ID:?}
ELANQUANT_ONLINE_ROOT=${ELANQUANT_ONLINE_ROOT:?}
PYTHON_BIN=${PYTHON_BIN:?}
ELANQUANT_UPSTREAM_ROOT=${ELANQUANT_UPSTREAM_ROOT:?}
RESEARCH_DEPS=${RESEARCH_DEPS:?}
export PYTHONPATH="$RESEARCH_DEPS${PYTHONPATH:+:$PYTHONPATH}"

SOURCE=${ELANQUANT_SOURCE:-$ELANQUANT_ROOT/source}
TRAIN_ROOT=$ELANQUANT_ROOT/runs/training/$ELANQUANT_RUN_ID
EVAL_ROOT=$ELANQUANT_ROOT/runs/evaluation/$ELANQUANT_RUN_ID
MATRIX=$TRAIN_ROOT/matrix.json
SMOKE=$EVAL_ROOT/smoke-evaluation.json
FORMAL=$EVAL_ROOT/formal-evaluation.json
SMALL_RELEASE=${ELANQUANT_SMALL_RELEASE:?}
CATALOG=${ELANQUANT_RESEARCH_CATALOG:-$ELANQUANT_ROOT/releases/research-catalog.json}

[[ -f "$MATRIX" ]] || {
  echo "missing sealed Base matrix: $MATRIX" >&2
  exit 66
}
for target in "$SMOKE" "$FORMAL"; do
  [[ ! -e "$target" ]] || {
    echo "immutable Base evaluation output already exists; use a new run id: $target" >&2
    exit 73
  }
done
[[ ! -e "$CATALOG" ]] || {
  echo "research catalog already exists; inspect it before any replacement: $CATALOG" >&2
  exit 73
}

terminals=(
  "$TRAIN_ROOT/official-tokenizer-base/terminal.json"
  "$TRAIN_ROOT/official-predictor-base/terminal.json"
  "$TRAIN_ROOT/strict-tokenizer-base/terminal.json"
  "$TRAIN_ROOT/strict-predictor-base/terminal.json"
)
for terminal in "${terminals[@]}"; do
  [[ -f "$terminal" ]] || { echo "missing terminal receipt: $terminal" >&2; exit 66; }
  "$PYTHON_BIN" - "$terminal" <<'PY'
import json
import pathlib
import sys

receipt = json.loads(pathlib.Path(sys.argv[1]).read_text())
raise SystemExit(0 if receipt.get("status") == "PASS" else 1)
PY
done

[[ -f "$SMALL_RELEASE/training-matrix.json" ]] || {
  echo "missing immutable Small matrix: $SMALL_RELEASE" >&2
  exit 66
}
[[ -f "$SMALL_RELEASE/formal-evaluation.json" ]] || {
  echo "missing immutable Small evaluation: $SMALL_RELEASE" >&2
  exit 66
}

mkdir -p "$EVAL_ROOT"
cd "$SOURCE"
export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0}

"$PYTHON_BIN" scripts/server/evaluate_and_infer.py \
  --root "$ELANQUANT_ROOT" \
  --upstream "$ELANQUANT_UPSTREAM_ROOT" \
  --matrix-receipt "$MATRIX" \
  --model-size base \
  --online-root "$ELANQUANT_ONLINE_ROOT" \
  --smoke-evaluation-samples 600 \
  --batch-size 50 \
  --online-batch-size 50 \
  --out "$SMOKE"

"$PYTHON_BIN" scripts/server/evaluate_and_infer.py \
  --root "$ELANQUANT_ROOT" \
  --upstream "$ELANQUANT_UPSTREAM_ROOT" \
  --matrix-receipt "$MATRIX" \
  --model-size base \
  --online-root "$ELANQUANT_ONLINE_ROOT" \
  --formal-sessions-per-month 5 \
  --batch-size 50 \
  --online-batch-size 50 \
  --out "$FORMAL"

"$PYTHON_BIN" scripts/server/build_research_catalog.py \
  --small-matrix "$SMALL_RELEASE/training-matrix.json" \
  --small-evaluation "$SMALL_RELEASE/formal-evaluation.json" \
  --base-matrix "$MATRIX" \
  --base-evaluation "$FORMAL" \
  --out "$CATALOG"

echo "Base candidate evaluation resumed and catalogued without promotion: $ELANQUANT_RUN_ID"
