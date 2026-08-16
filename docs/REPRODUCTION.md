# 完整复现 / Full Reproduction

[English README](../README.en.md) · [简体中文 README](../README.md)

本指南复现 ElanQuant 的**方法、代码与证据链**。它不会捏造“任何人都能获得同一份
行情数据”的承诺：A 股原始行情、CSI300 历史成员资格和数据供应商修订受许可证与
可得性约束。若要得到字节一致的研究结果，复现者必须拥有同一份经许可的、封存的数据
快照及其 manifest；否则应得到一个新的、诚实标注的数据身份和新回执。

## 0. 两条复现路线

| 路线 | 需要什么 | 可以验证什么 |
| --- | --- | --- |
| Portable | Python 3.11+、Node、公开权重网络访问 | CLI、数据契约、合成 smoke、前端与单标零样本工作流 |
| Full research | Linux/NVIDIA、CUDA、Qlib、用户持有的 PIT 数据与日历 | 四模型训练、滚动测试、Top50/Top3、持仓和封存 release |

不要在 macOS 上执行数据下载、正式训练、正式评估或历史回测。Apple Silicon profile
用于 Small 本地推理前置检查和可移植性验证；完整研究在你自己的 Linux/NVIDIA 主机上进行。

## 1. 固定源码与环境

```bash
git clone https://github.com/elan6666/ElanQuant.git
cd ElanQuant
git rev-parse HEAD                 # 写入你的复现日志
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,repro,inference]'

git clone https://github.com/shiyu-coder/Kronos.git .elanquant/upstream/Kronos
git -C .elanquant/upstream/Kronos checkout 67b630e67f6a18c9e9be918d9b4337c960db1e9a
test "$(git -C .elanquant/upstream/Kronos rev-parse HEAD)" = \
  67b630e67f6a18c9e9be918d9b4337c960db1e9a
```

Fetch and hash the official public weights before any model operation:

```bash
elanquant bootstrap --profile remote-linux-nvidia --release small
elanquant bootstrap --profile remote-linux-nvidia --release base
```

Save `bootstrap-receipt.json`, the upstream commit and `pip freeze` outside
Git. No secret, raw data, model file, checkpoint or generated report belongs in
the repository.

## 2. Prepare point-in-time data

Your daily input must use `instrument,timestamp,open,high,low,close` and may
include `volume,amount`. Import it with a named calendar, universe policy,
PIT declaration and source licence:

```bash
elanquant data import \
  --input /secure/input/daily-bars.parquet \
  --output /secure/elanquant/input/daily-bars.parquet \
  --calendar csi300-exchange-calendar-v1 \
  --universe-policy csi300-pit-next-session-v1 \
  --pit-declaration "membership becomes eligible on the next exchange session" \
  --source-license "YOUR-LICENSE-ID"
```

For the official-style research route, materialise a separate immutable data
root with `scripts/server/fetch_official_split_raw_v3.py`, then run
`materialize_official_split_dataset_v3.py` and
`audit_official_split_dataset_v3.py`. The audit must pass before training.

Required controls:

1. Membership at signal date is known at or before the declared availability
   time; incomplete snapshots are explicitly excluded rather than filled.
2. Candidate eligibility uses only the 90 prior **global exchange sessions**.
   It must not require that a symbol survives for a future horizon.
3. Future ten sessions are used only to construct mature labels, with the
   configured missing-session policy recorded in the receipt.
4. Every file is inventory-hashed, and every train/validation/test effective
   window is independently checked.

## 3. Train the two official-style fine-tunes

Only `small-official-ft` and `base-official-ft` run the tokenizer → predictor
training chain. Zero-shot cells reference the pinned public weights. Choose a
new immutable run ID for each size; an existing output directory is a hard
failure.

```bash
export ELANQUANT_ROOT=/secure/elanquant
export PYTHON_BIN="$ELANQUANT_ROOT/.venv/bin/python"
export ELANQUANT_WORKSPACE="$ELANQUANT_ROOT/workspaces/kronos-official-split-v3"
export ELANQUANT_FROZEN_LATEST=YYYY-MM-DD
export ELANQUANT_DATA_MANIFEST="$ELANQUANT_ROOT/data/official-split-v3/manifest.json"
export ELANQUANT_DATASET_PATH="$ELANQUANT_ROOT/data/official-split-v3/official"

# Small; repeat with MODEL_SIZE=base and a different immutable run id.
export ELANQUANT_MODEL_SIZE=small
export ELANQUANT_RUN_ID="kronos-small-official-ft-official-split-v3-YYYYMMDD"
export ELANQUANT_CONFIG_SOURCE="$PWD/configs/models/official_split_v3_small_official_ft.yaml"
bash scripts/server/run_official_split_training_v3.sh
```

The launcher rejects Strict-PIT identifiers, a mutable output path, a runtime
configuration mismatch or missing input manifest. It runs the author-aligned
30-epoch stages and seals the selected checkpoint, log, config, input-weight
and data identities in terminal receipts.

Compile the four-cell matrix only after both fine-tunes have terminal receipts:

```bash
python scripts/server/compile_official_split_matrix_v3.py --help
```

Use the script's documented arguments to bind the two zero-shot and two
official-fine-tuned cells. Never modify a sealed matrix; start a new run when
any input changes.

## 4. Lock analysis before opening the rolling test

Create the analysis lock **before** signal or backtest results exist. It binds
the matrix, data/admission manifests, calendar, provider tree, Qlib identity,
signal/backtest source hashes, strategy constants and result root.

```bash
python scripts/server/build_official_split_analysis_lock_v3.py --help
```

Then run the four independent signals and eight portfolio studies:

```bash
bash scripts/server/run_official_split_analysis_v3.sh
```

The resulting matrix is exactly:

| Cells | Portfolios | Signal protocol |
| --- | --- | --- |
| Small/Base × zero-shot/official-ft | Top50/Drop5/Hold5 and Top3/Drop1/Hold5 | 90-session normalisation, 10-session horizon, 5 sampled paths |

Top3 is a historical Qlib sensitivity study, not the online paper account. Its
actual holding count can differ from three because Qlib holds/tradability and
cash constraints are part of the sealed execution semantics.

## 5. Seal, audit and publish safely

Use `seal_official_split_catalogs_v3.py` to consume actual receipts/artifacts;
do not hand-write catalog JSON. Use the corresponding audit script to rehash
all inputs, signals, daily reports, holdings, strategies and current-release
boundary. Set sealed files read-only only after successful audit.

The online Small release requires an additional pre-result online-method lock.
It binds the primary model, online signal protocol and source hashes before the
viewed results are produced. Base may write research scores but must report
`RESEARCH_ONLY_NOT_PUBLISHED` and must create no recommendation, order,
position, NAV or paper-account row.

`TEST_VIEWED` results are descriptive, never model/strategy promotion evidence.
Release admission must fail closed if a hash, source path, candidate set,
manifest or lock does not match.

## 6. Final verification

```bash
python -m pytest -q
ruff check backend scripts tests
pyright --pythonpath .venv/bin/python backend/src scripts/research
python -m compileall -q backend/src tests scripts

npm --prefix frontend test -- --run
npm --prefix frontend run lint
npm --prefix frontend run build
```

On the deployment host, additionally validate the release pair, run only
read-only API GET checks, compare paper-ledger tables before/after Base research
execution, and ensure the service binds loopback rather than a public address.

## What to publish

Safe to publish: source, configs, documentation, synthetic fixtures, hashes,
receipts without secrets, and source manifests that do not disclose protected
data.

Do not publish without explicit rights: raw/processed vendor data, credentials,
provider responses, fine-tuned checkpoints, training logs, predictions or
private database files. MIT source licensing does not override Kronos or market
data licences.
