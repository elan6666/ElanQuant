#!/usr/bin/env bash
set -euo pipefail

ELANQUANT_ROOT=${ELANQUANT_ROOT:?}
PYTHON_BIN=${PYTHON_BIN:?}
RESEARCH_DEPS=${RESEARCH_DEPS:?}
ELANQUANT_RUN_ID=${ELANQUANT_RUN_ID:?}
ELANQUANT_WORKSPACE_ROOT=${ELANQUANT_WORKSPACE_ROOT:?}
export ELANQUANT_ROOT
export PYTHONPATH="$RESEARCH_DEPS"
export TOKENIZERS_PARALLELISM=false
export PYTHONUNBUFFERED=1
# The two consumer GPUs sit behind different NUMA/PCIe host bridges and expose
# no NVLink.  Direct peer transport hangs NCCL initialization on this server;
# socket/shared-memory collectives are the verified two-GPU path.
export NCCL_P2P_DISABLE=${NCCL_P2P_DISABLE:-1}
export NCCL_IB_DISABLE=${NCCL_IB_DISABLE:-1}
# A 64 MiB two-rank admission collective fails with CUDA illegal-access when
# NCCL uses cross-NUMA shared memory on this host.  Loopback sockets pass the
# same collective and a full Kronos DDP forward/backward admission test.
export NCCL_SHM_DISABLE=${NCCL_SHM_DISABLE:-1}
export NCCL_SOCKET_IFNAME=${NCCL_SOCKET_IFNAME:-lo}
export ELANQUANT_WORLD_SIZE=${ELANQUANT_WORLD_SIZE:-2}
ELANQUANT_MODEL_SIZE_ONLY=${ELANQUANT_MODEL_SIZE_ONLY:-small}
if [[ "$ELANQUANT_MODEL_SIZE_ONLY" != small && "$ELANQUANT_MODEL_SIZE_ONLY" != base ]]; then
  echo "ELANQUANT_MODEL_SIZE_ONLY must be small or base" >&2
  exit 64
fi

export ELANQUANT_RECEIPT_ROOT=${ELANQUANT_RECEIPT_ROOT:-$ELANQUANT_ROOT/runs/training/$ELANQUANT_RUN_ID}
export ELANQUANT_SAVE_ROOT=${ELANQUANT_SAVE_ROOT:-$ELANQUANT_ROOT/models/training/$ELANQUANT_RUN_ID}
if [[ -e "$ELANQUANT_RECEIPT_ROOT" || -e "$ELANQUANT_SAVE_ROOT" ]]; then
  if [[ ${ELANQUANT_RESUME_RUN:-0} != 1 ]]; then
    echo "immutable training run already exists: $ELANQUANT_RUN_ID" >&2
    exit 73
  fi
fi
mkdir -p "$ELANQUANT_RECEIPT_ROOT" "$ELANQUANT_SAVE_ROOT"

run_stage() {
  local track=$1
  local stage=$2
  local size=${3:-small}
  local workspace="$ELANQUANT_WORKSPACE_ROOT/$track"
  local receipt_root=${ELANQUANT_RECEIPT_ROOT:-$ELANQUANT_ROOT/runs/training}
  local receipt_dir="$receipt_root/$track-$stage-$size"
  if [[ -e "$receipt_dir" ]]; then
    if [[ ${ELANQUANT_RESUME_RUN:-0} == 1 ]] && python3 - "$receipt_dir/terminal.json" <<'PY'
import hashlib, json, pathlib, sys
path = pathlib.Path(sys.argv[1])
if not path.is_file():
    raise SystemExit(1)
receipt = json.loads(path.read_text())
checkpoint = pathlib.Path(str(receipt.get("checkpoint_path", "")))
if receipt.get("status") != "PASS" or not receipt.get("checkpoint_created_by_this_stage"):
    raise SystemExit(1)
if not checkpoint.is_file():
    raise SystemExit(1)
digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
raise SystemExit(0 if digest == receipt.get("checkpoint_sha256") else 1)
PY
    then
      echo "resume: verified sealed stage $track/$stage/$size"
      return 0
    fi
    echo "resume refused non-terminal or invalid stage: $receipt_dir" >&2
    return 73
  fi
  mkdir -p "$receipt_dir"
  export ELANQUANT_TRACK="$track"
  export ELANQUANT_MODEL_SIZE="$size"
  cd "$workspace/finetune"
  local script
  if [[ "$stage" == tokenizer ]]; then
    script=train_tokenizer.py
  else
    script=train_predictor.py
  fi
  local started
  started=$(date -Iseconds)
  local started_epoch
  started_epoch=$(date +%s)
  set +e
  "$PYTHON_BIN" -m torch.distributed.run --standalone \
    --nproc_per_node="$ELANQUANT_WORLD_SIZE" "$script" \
    >"$receipt_dir/output.log" 2>&1
  local code=$?
  set -e
  local save_root=${ELANQUANT_SAVE_ROOT:-$ELANQUANT_ROOT/models/finetuned}
  python3 - "$receipt_dir/terminal.json" "$track" "$stage" "$size" "$started" "$started_epoch" "$code" "$ELANQUANT_ROOT" "$save_root" "$workspace" <<'PY'
import hashlib, json, os, pathlib, sys
path, track, stage, size, started, started_epoch, code, root, save_root, workspace = sys.argv[1:]
log = pathlib.Path(path).with_name("output.log")
root_path = pathlib.Path(root)
workspace_path = pathlib.Path(workspace)
checkpoint = pathlib.Path(save_root) / track
checkpoint = checkpoint / ("tokenizer" if stage == "tokenizer" else f"predictor-{size}")
checkpoint = checkpoint / "checkpoints" / "best_model" / "model.safetensors"
def digest(candidate):
    if not candidate.is_file():
        return None
    h = hashlib.sha256()
    with candidate.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
def tree_digest(candidate):
    h = hashlib.sha256()
    for item in sorted(path for path in candidate.rglob("*") if path.is_file() and ".git" not in path.parts):
        h.update(item.relative_to(candidate).as_posix().encode())
        h.update(bytes.fromhex(digest(item)))
    return h.hexdigest()
checkpoint_fresh = checkpoint.is_file() and checkpoint.stat().st_mtime >= int(started_epoch)
input_tokenizer = (
    root_path / "models/pretrained/Kronos-Tokenizer-base/model.safetensors"
    if stage == "tokenizer"
    else pathlib.Path(save_root) / track / "tokenizer/checkpoints/best_model/model.safetensors"
)
input_predictor = root_path / f"models/pretrained/Kronos-{size}/model.safetensors"
payload = {
    "schema_version": "elanquant_training_terminal_v2",
    "track": track,
    "stage": stage,
    "size": size,
    "started_at": started,
    "finished_at": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(),
    "exit_code": int(code),
    "status": "PASS" if int(code) == 0 else "FAILED",
    "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
    "checkpoint_path": str(checkpoint),
    "checkpoint_sha256": digest(checkpoint),
    "checkpoint_created_by_this_stage": checkpoint_fresh,
    "data_manifest_sha256": digest(root_path / "data/processed/extended-v2/manifest.json"),
    "workspace_receipt_sha256": digest(pathlib.Path(os.environ["ELANQUANT_WORKSPACE_ROOT"]) / "receipt.json"),
    "runtime_workspace_tree_sha256": tree_digest(workspace_path),
    "runtime_config_sha256": digest(workspace_path / "finetune/config.py"),
    "runtime_dataset_sha256": digest(workspace_path / "finetune/dataset.py"),
    "runtime_training_script_sha256": digest(
        workspace_path / "finetune" / ("train_tokenizer.py" if stage == "tokenizer" else "train_predictor.py")
    ),
    "input_tokenizer_sha256": digest(input_tokenizer),
    "input_predictor_sha256": digest(input_predictor),
    "effective_parameters": {
        "epochs": int(os.environ.get("ELANQUANT_EPOCHS", "30")),
        "batch_size_per_gpu": int(os.environ.get("ELANQUANT_BATCH_SIZE", "50")),
        "train_samples_per_epoch": int(os.environ.get("ELANQUANT_TRAIN_SAMPLES", "100000")),
        "validation_samples_per_epoch": int(os.environ.get("ELANQUANT_VAL_SAMPLES", "20000")),
        "world_size": int(os.environ.get("ELANQUANT_WORLD_SIZE", "2")),
        "seed": 100,
        "optimizer": {
            "tokenizer_lr": 2e-4,
            "predictor_lr": 4e-5,
            "betas": [0.9, 0.95],
            "weight_decay": 0.1,
        },
        "scheduler": "author_OneCycleLR_unchanged",
        "accumulation_steps": 1,
        "nccl": {
            "p2p_disable": os.environ.get("NCCL_P2P_DISABLE"),
            "ib_disable": os.environ.get("NCCL_IB_DISABLE"),
            "shm_disable": os.environ.get("NCCL_SHM_DISABLE"),
            "socket_ifname": os.environ.get("NCCL_SOCKET_IFNAME"),
        },
    },
}
if int(code) == 0 and (payload["checkpoint_sha256"] is None or not checkpoint_fresh):
    payload["status"] = "FAILED"
    payload["receipt_error"] = "training exited zero but checkpoint is missing or stale"
pathlib.Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
PY
  if [[ $code -eq 0 ]]; then
    if ! python3 - "$receipt_dir/terminal.json" <<'PY'
import json, pathlib, sys
raise SystemExit(0 if json.loads(pathlib.Path(sys.argv[1]).read_text())["status"] == "PASS" else 86)
PY
    then
      code=86
    fi
  fi
  if [[ $code -ne 0 ]]; then
    return "$code"
  fi
}

run_track() {
  local track=$1
  local visible_gpu=$2
  export CUDA_VISIBLE_DEVICES=$visible_gpu
  export ELANQUANT_WORLD_SIZE=1
  run_stage "$track" tokenizer "$ELANQUANT_MODEL_SIZE_ONLY"
  run_stage "$track" predictor "$ELANQUANT_MODEL_SIZE_ONLY"
}

if [[ ${ELANQUANT_PARALLEL_TRACKS:-0} == 1 ]]; then
  # Each complete track remains an unmodified one-rank author training run.
  # Running the two independent tracks concurrently is a scheduling choice,
  # not model/data coupling, and avoids cross-NUMA NCCL communication entirely.
  run_track official 0 &
  official_pid=$!
  run_track strict 1 &
  strict_pid=$!
  wait "$official_pid"
  wait "$strict_pid"
else
  run_stage official tokenizer "$ELANQUANT_MODEL_SIZE_ONLY"
  run_stage official predictor "$ELANQUANT_MODEL_SIZE_ONLY"
  run_stage strict tokenizer "$ELANQUANT_MODEL_SIZE_ONLY"
  run_stage strict predictor "$ELANQUANT_MODEL_SIZE_ONLY"
fi
