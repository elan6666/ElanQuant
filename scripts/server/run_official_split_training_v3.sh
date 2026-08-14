#!/usr/bin/env bash
set -euo pipefail

# Server-only launcher.  Zero-shot cells never enter this script; only the two
# official tokenizer -> predictor fine-tunes are executable.
ELANQUANT_ROOT=${ELANQUANT_ROOT:?}
PYTHON_BIN=${PYTHON_BIN:?}
ELANQUANT_WORKSPACE=${ELANQUANT_WORKSPACE:?}
ELANQUANT_MODEL_SIZE=${ELANQUANT_MODEL_SIZE:?}
ELANQUANT_RUN_ID=${ELANQUANT_RUN_ID:?}
ELANQUANT_FROZEN_LATEST=${ELANQUANT_FROZEN_LATEST:?}
ELANQUANT_DATA_MANIFEST=${ELANQUANT_DATA_MANIFEST:?}
ELANQUANT_CONFIG_SOURCE=${ELANQUANT_CONFIG_SOURCE:?}
ELANQUANT_DATASET_PATH=${ELANQUANT_DATASET_PATH:?}

if [[ "$ELANQUANT_MODEL_SIZE" != small && "$ELANQUANT_MODEL_SIZE" != base ]]; then
  echo "model size must be small or base" >&2
  exit 64
fi
if [[ "$ELANQUANT_RUN_ID" != *-official-ft-official-split-v3-* ]]; then
  echo "run id must identify an immutable official-ft official-split-v3 run" >&2
  exit 64
fi
if [[ "$ELANQUANT_WORKSPACE" == *strict* || "$ELANQUANT_RUN_ID" == *strict* ]]; then
  echo "Plan011 forbids new strict-PIT training" >&2
  exit 64
fi
if [[ ! -f "$ELANQUANT_DATA_MANIFEST" || ! -f "$ELANQUANT_CONFIG_SOURCE" ]]; then
  echo "sealed data manifest and reviewed runtime config are required" >&2
  exit 66
fi
if ! cmp -s "$ELANQUANT_CONFIG_SOURCE" "$ELANQUANT_WORKSPACE/finetune/config.py"; then
  echo "workspace config does not match reviewed official-split-v3 config" >&2
  exit 65
fi

RUN_ROOT="$ELANQUANT_ROOT/runs/training/$ELANQUANT_RUN_ID"
SAVE_ROOT="$ELANQUANT_ROOT/models/training/$ELANQUANT_RUN_ID"
if [[ -e "$RUN_ROOT" || -e "$SAVE_ROOT" ]]; then
  echo "immutable run already exists: $ELANQUANT_RUN_ID" >&2
  exit 73
fi
mkdir -p "$RUN_ROOT" "$SAVE_ROOT"

export ELANQUANT_ROOT ELANQUANT_MODEL_SIZE ELANQUANT_RUN_ID ELANQUANT_FROZEN_LATEST
export ELANQUANT_DATASET_PATH
export ELANQUANT_TRACK=official
export ELANQUANT_SAVE_ROOT="$SAVE_ROOT"
export TOKENIZERS_PARALLELISM=false
export PYTHONUNBUFFERED=1

run_stage() {
  local stage=$1
  local script
  local started_epoch
  started_epoch=$(date +%s)
  if [[ "$stage" == tokenizer ]]; then
    script=train_tokenizer.py
  else
    script=train_predictor.py
  fi
  mkdir "$RUN_ROOT/$stage"
  (
    cd "$ELANQUANT_WORKSPACE/finetune"
    "$PYTHON_BIN" -m torch.distributed.run --standalone \
      --nproc_per_node="${ELANQUANT_WORLD_SIZE:-2}" "$script"
  ) >"$RUN_ROOT/$stage/output.log" 2>&1
  local checkpoint
  local input_tokenizer_args=()
  if [[ "$stage" == tokenizer ]]; then
    checkpoint="$SAVE_ROOT/official/tokenizer/checkpoints/best_model/model.safetensors"
  else
    checkpoint="$SAVE_ROOT/official/predictor-$ELANQUANT_MODEL_SIZE/checkpoints/best_model/model.safetensors"
    input_tokenizer_args=(
      --input-tokenizer
      "$SAVE_ROOT/official/tokenizer/checkpoints/best_model/model.safetensors"
    )
  fi
  "$PYTHON_BIN" "$ELANQUANT_ROOT/source/scripts/server/build_training_terminal_v3.py" \
    --cell-id "$ELANQUANT_MODEL_SIZE-official-ft" \
    --stage "$stage" \
    --run-id "$ELANQUANT_RUN_ID" \
    --started-epoch "$started_epoch" \
    --log "$RUN_ROOT/$stage/output.log" \
    --checkpoint "$checkpoint" \
    --data-manifest "$ELANQUANT_DATA_MANIFEST" \
    --config "$ELANQUANT_CONFIG_SOURCE" \
    "${input_tokenizer_args[@]}" \
    --input-predictor "$ELANQUANT_ROOT/models/pretrained/Kronos-$ELANQUANT_MODEL_SIZE/model.safetensors" \
    --out "$RUN_ROOT/$stage/terminal.json"
}

run_stage tokenizer
run_stage predictor
