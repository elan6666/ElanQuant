#!/usr/bin/env bash
set -euo pipefail

# Compile and evaluate an already-running causal official-split training run.
# This script creates an immutable candidate release but never updates
# releases/current. Promotion remains a separate, reviewed operation.

ELANQUANT_ROOT=${ELANQUANT_ROOT:?}
PYTHON_BIN=${PYTHON_BIN:?}
TRAINING_PYTHON=${TRAINING_PYTHON:-$PYTHON_BIN}
QLIB_PYTHON=${QLIB_PYTHON:?}
QLIB_SITE_PACKAGES=${QLIB_SITE_PACKAGES:?}
UPSTREAM_ROOT=${UPSTREAM_ROOT:?}
DATASET_ROOT=${DATASET_ROOT:?}
DATASET_ADMISSION=${DATASET_ADMISSION:?}
PROVIDER_RECEIPT=${PROVIDER_RECEIPT:?}
TRADE_CALENDAR=${TRADE_CALENDAR:?}
WORKSPACE=${WORKSPACE:?}
SMALL_TRAINING_RUN_ID=${SMALL_TRAINING_RUN_ID:?}
BASE_TRAINING_RUN_ID=${BASE_TRAINING_RUN_ID:?}
EVIDENCE_RUN_ID=${EVIDENCE_RUN_ID:?}
RELEASE_ID=${RELEASE_ID:?}

SOURCE_ROOT="$ELANQUANT_ROOT/source"
MANIFEST="$DATASET_ROOT/manifest.json"
EVIDENCE_ROOT="$ELANQUANT_ROOT/runs/official-split-v3/$EVIDENCE_RUN_ID"
MATRIX_ROOT="$ELANQUANT_ROOT/runs/training/$EVIDENCE_RUN_ID"
RESULTS_ROOT="$ELANQUANT_ROOT/runs/analysis/$EVIDENCE_RUN_ID"
RELEASE_ROOT="$ELANQUANT_ROOT/releases/$RELEASE_ID"

SPLIT_RECEIPT="$EVIDENCE_ROOT/split-receipt.json"
TRAINING_AUDIT="$EVIDENCE_ROOT/training-fidelity-audit.json"
MATRIX_SOURCE="$EVIDENCE_ROOT/matrix-source.json"
RETIREMENT_SOURCE="$EVIDENCE_ROOT/retirement-source.json"
ANALYSIS_LOCK="$EVIDENCE_ROOT/analysis-lock.json"
ONLINE_METHOD_LOCK="$EVIDENCE_ROOT/online-method-lock.json"
MATRIX="$MATRIX_ROOT/matrix.json"
RETIREMENT="$MATRIX_ROOT/strict-pit-retirement.json"
EVALUATION="$EVIDENCE_ROOT/rolling-evaluation.json"
HISTORICAL="$EVIDENCE_ROOT/historical-catalog.json"

terminal_paths=(
  "$ELANQUANT_ROOT/runs/training/$SMALL_TRAINING_RUN_ID/tokenizer/terminal.json"
  "$ELANQUANT_ROOT/runs/training/$SMALL_TRAINING_RUN_ID/predictor/terminal.json"
  "$ELANQUANT_ROOT/runs/training/$BASE_TRAINING_RUN_ID/tokenizer/terminal.json"
  "$ELANQUANT_ROOT/runs/training/$BASE_TRAINING_RUN_ID/predictor/terminal.json"
)
while true; do
  complete=true
  for path in "${terminal_paths[@]}"; do
    if [[ ! -f "$path" ]]; then
      complete=false
      break
    fi
  done
  if [[ "$complete" == true ]]; then
    break
  fi
  sleep 30
done

for path in \
  "$SPLIT_RECEIPT" "$TRAINING_AUDIT" "$MATRIX_SOURCE" \
  "$RETIREMENT_SOURCE" "$ANALYSIS_LOCK" "$ONLINE_METHOD_LOCK" \
  "$MATRIX" "$RETIREMENT" "$EVALUATION" "$HISTORICAL"; do
  if [[ -e "$path" ]]; then
    echo "immutable evidence output already exists: $path" >&2
    exit 73
  fi
done
if [[ -e "$RESULTS_ROOT" || -e "$RELEASE_ROOT" ]]; then
  echo "immutable results or release output already exists" >&2
  exit 73
fi

cd "$SOURCE_ROOT"
export PYTHONPATH="$SOURCE_ROOT/backend/src:$SOURCE_ROOT:$SOURCE_ROOT/scripts/server"
mkdir -p "$EVIDENCE_ROOT" "$MATRIX_ROOT"

"$TRAINING_PYTHON" - "$MANIFEST" "$SPLIT_RECEIPT" <<'PY'
import json
import os
import sys
from pathlib import Path

from scripts.research.official_split_v3 import validate_split_receipt

manifest_path, output_path = map(Path, sys.argv[1:])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
split = validate_split_receipt(manifest["split_contract"])
temporary = output_path.with_suffix(output_path.suffix + f".tmp-{os.getpid()}")
temporary.write_text(json.dumps(split, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.replace(temporary, output_path)
PY

"$TRAINING_PYTHON" scripts/server/build_training_fidelity_audit_v3.py \
  --root "$ELANQUANT_ROOT" \
  --workspace "$WORKSPACE" \
  --weights-receipt "$ELANQUANT_ROOT/models/pretrained/receipt.json" \
  --dataset-manifest "$MANIFEST" \
  --dataset-admission "$DATASET_ADMISSION" \
  --training-runner "$SOURCE_ROOT/scripts/server/run_official_split_training_v3.sh" \
  --terminal-builder "$SOURCE_ROOT/scripts/server/build_training_terminal_v3.py" \
  --small-run-id "$SMALL_TRAINING_RUN_ID" \
  --base-run-id "$BASE_TRAINING_RUN_ID" \
  --out "$TRAINING_AUDIT"

"$TRAINING_PYTHON" scripts/server/build_official_split_matrix_source_v3.py \
  --root "$ELANQUANT_ROOT" \
  --run-id "$EVIDENCE_RUN_ID" \
  --small-training-run-id "$SMALL_TRAINING_RUN_ID" \
  --base-training-run-id "$BASE_TRAINING_RUN_ID" \
  --small-legacy-matrix "$ELANQUANT_ROOT/runs/training/kronos-a-share-v2-20260813/matrix.json" \
  --base-legacy-matrix "$ELANQUANT_ROOT/runs/training/kronos-base-a-share-v1-20260813/matrix.json" \
  --matrix-source-out "$MATRIX_SOURCE" \
  --retirement-source-out "$RETIREMENT_SOURCE"

"$TRAINING_PYTHON" scripts/server/compile_official_split_matrix_v3.py \
  --root "$ELANQUANT_ROOT" \
  --source "$MATRIX_SOURCE" \
  --split-receipt "$SPLIT_RECEIPT" \
  --dataset-manifest "$MANIFEST" \
  --dataset-admission "$DATASET_ADMISSION" \
  --weights-receipt "$ELANQUANT_ROOT/models/pretrained/receipt.json" \
  --training-audit "$TRAINING_AUDIT" \
  --out "$MATRIX" \
  --retirement-source "$RETIREMENT_SOURCE" \
  --retirement-out "$RETIREMENT"

"$QLIB_PYTHON" scripts/server/build_official_split_analysis_lock_v3.py \
  --root "$ELANQUANT_ROOT" \
  --matrix "$MATRIX" \
  --dataset-manifest "$MANIFEST" \
  --dataset-admission "$DATASET_ADMISSION" \
  --provider-receipt "$PROVIDER_RECEIPT" \
  --signal-runner "$SOURCE_ROOT/scripts/server/run_official_split_signals_v3.py" \
  --signal-helper "$SOURCE_ROOT/scripts/server/generate_official_demo_signals.py" \
  --evaluation-helper "$SOURCE_ROOT/scripts/server/evaluate_and_infer.py" \
  --backtest-runner "$SOURCE_ROOT/scripts/server/run_official_split_backtest_v3.py" \
  --backtest-helper "$SOURCE_ROOT/scripts/server/run_historical_top3_variant.py" \
  --qlib-site-packages "$QLIB_SITE_PACKAGES" \
  --trade-calendar "$TRADE_CALENDAR" \
  --results-root "$RESULTS_ROOT" \
  --out "$ANALYSIS_LOCK"

"$TRAINING_PYTHON" scripts/server/build_official_split_online_method_lock_v3.py \
  --root "$ELANQUANT_ROOT" \
  --matrix "$MATRIX" \
  --online-runner "$SOURCE_ROOT/scripts/server/evaluate_official_split_online_v3.py" \
  --viewed-results-root "$RESULTS_ROOT" \
  --out "$ONLINE_METHOD_LOCK"

ELANQUANT_ROOT="$ELANQUANT_ROOT" \
PYTHON_BIN="$TRAINING_PYTHON" \
UPSTREAM_ROOT="$UPSTREAM_ROOT" \
QLIB_SITE_PACKAGES="$QLIB_SITE_PACKAGES" \
ANALYSIS_LOCK="$ANALYSIS_LOCK" \
MATRIX_RECEIPT="$MATRIX" \
DATASET_MANIFEST="$MANIFEST" \
DATASET_ADMISSION="$DATASET_ADMISSION" \
TRADE_CALENDAR="$TRADE_CALENDAR" \
RESULTS_ROOT="$RESULTS_ROOT" \
DEVICE=cuda:0 \
  "$SOURCE_ROOT/scripts/server/run_official_split_analysis_v3.sh"

"$TRAINING_PYTHON" scripts/server/seal_official_split_catalogs_v3.py \
  --root "$ELANQUANT_ROOT" \
  --analysis-lock "$ANALYSIS_LOCK" \
  --results-root "$RESULTS_ROOT" \
  --evaluation-out "$EVALUATION" \
  --historical-out "$HISTORICAL"

"$TRAINING_PYTHON" scripts/server/publish_official_split_online_release_v3.py \
  --root "$ELANQUANT_ROOT" \
  --release-id "$RELEASE_ID" \
  --matrix "$MATRIX" \
  --analysis-lock "$ANALYSIS_LOCK" \
  --online-method-lock "$ONLINE_METHOD_LOCK" \
  --evaluation "$EVALUATION" \
  --historical "$HISTORICAL" \
  --online-runner "$SOURCE_ROOT/scripts/server/evaluate_official_split_online_v3.py" \
  --out-dir "$RELEASE_ROOT"

echo "candidate release complete; releases/current was not changed: $RELEASE_ID"
