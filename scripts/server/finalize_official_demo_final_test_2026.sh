#!/usr/bin/env bash
set -euo pipefail

ROOT=${ELANQUANT_ROOT:-/data/yilangliu/a_share_research/elanquant}
SOURCE=${ELANQUANT_SOURCE:-$ROOT/source}
RUN=${ELANQUANT_FINAL_TEST_RUN:-$ROOT/runs/backtests/official-demo-method-final-test-2026-v1-20260813}
VALIDATION_RUN=${ELANQUANT_VALIDATION_RUN:-$ROOT/runs/backtests/official-demo-method-v1-20260813}
RESEARCH_PYTHON=${ELANQUANT_RESEARCH_PYTHON:-/data/yilangliu/a_share_research/seven_model_research/.venv/bin/python}
APP_PYTHON=${ELANQUANT_APP_PYTHON:-$ROOT/app-venv/bin/python}
QLIB_SITE=${ELANQUANT_QLIB_SITE:-/data/yilangliu/a_share_research/alphagen-venv/lib/python3.12/site-packages}
export PYTHONPATH="$SOURCE/backend/src:$ROOT/research-deps${PYTHONPATH:+:$PYTHONPATH}"
MATRIX=$ROOT/releases/current/training-matrix.json
MANIFEST=$ROOT/data/processed/extended-v2/manifest.json
DATASET=$ROOT/data/processed/extended-v2/official/test_data.pkl
VALIDATION_RECEIPT=$VALIDATION_RUN/result/backtest-receipt.json
LOCK=$RUN/analysis-lock-receipt.json
BENCHMARK=$RUN/benchmark
PROVIDER=$RUN/qlib-provider
SIGNALS=$RUN/signals
RESULT=$RUN/result
CATALOG=$ROOT/releases/historical-backtest-catalog-v3.json
BEFORE=$RUN/paper-boundary-before.json
AFTER=$RUN/paper-boundary-after.json

cd "$SOURCE"
[[ ! -e "$RUN" ]] || { echo "final-test run already exists" >&2; exit 1; }
[[ ! -e "$CATALOG" ]] || { echo "v2 historical catalog already exists" >&2; exit 1; }
[[ -f "$VALIDATION_RECEIPT" && -f "$MATRIX" && -f "$MANIFEST" && -f "$DATASET" ]] || {
  echo "sealed final-test inputs are incomplete" >&2
  exit 1
}
mkdir -p "$RUN"

"$APP_PYTHON" scripts/server/audit_paper_boundary.py \
  --database "$ROOT/artifacts/elanquant.sqlite3" \
  --out "$BEFORE"

"$APP_PYTHON" scripts/server/build_official_demo_analysis_lock.py \
  --validation-backtest-receipt "$VALIDATION_RECEIPT" \
  --matrix "$MATRIX" \
  --dataset-manifest "$MANIFEST" \
  --dataset "$DATASET" \
  --out "$LOCK"

"$RESEARCH_PYTHON" scripts/server/fetch_official_demo_benchmark.py \
  --proxy-client /data/yilangliu/a_share_research/scripts/tushare_proxy_client.py \
  --out-dir "$BENCHMARK" \
  --start 2025-08-20 \
  --end 2026-08-12

"$RESEARCH_PYTHON" scripts/server/build_official_demo_qlib_provider.py \
  --root "$ROOT" \
  --dataset-manifest "$MANIFEST" \
  --dataset "$DATASET" \
  --benchmark-receipt "$BENCHMARK/receipt.json" \
  --dumper /data/yilangliu/a_share_research/upstream/alphagen/data_collection/qlib_dump_bin.py \
  --qlib-site-packages "$QLIB_SITE" \
  --evaluation-split test_viewed_2026 \
  --analysis-lock "$LOCK" \
  --out-dir "$PROVIDER"

"$RESEARCH_PYTHON" scripts/server/generate_official_demo_signals.py \
  --root "$ROOT" \
  --upstream "$ROOT/upstream/Kronos" \
  --matrix "$MATRIX" \
  --dataset-manifest "$MANIFEST" \
  --dataset "$DATASET" \
  --evaluation-split test_viewed_2026 \
  --analysis-lock "$LOCK" \
  --start 2026-01-01 \
  --end 2026-08-12 \
  --device cuda:0 \
  --out-dir "$SIGNALS"
cp "$SOURCE/scripts/server/generate_official_demo_signals.py" "$SIGNALS/generator-source.py"
chmod 400 "$SIGNALS/generator-source.py"

"$RESEARCH_PYTHON" scripts/server/run_official_demo_backtest.py \
  --root "$ROOT" \
  --signal-receipt "$SIGNALS/signal-receipt.json" \
  --provider-receipt "$PROVIDER/provider-receipt.json" \
  --analysis-lock "$LOCK" \
  --qlib-site-packages "$QLIB_SITE" \
  --out-dir "$RESULT"
cp "$SOURCE/scripts/server/run_official_demo_backtest.py" "$RESULT/backtest-source.py"
chmod 400 "$RESULT/backtest-source.py"

"$APP_PYTHON" scripts/server/build_official_demo_catalog.py \
  --root "$ROOT" \
  --backtest-receipt "$VALIDATION_RECEIPT" \
  --backtest-receipt "$RESULT/backtest-receipt.json" \
  --out "$CATALOG"

"$APP_PYTHON" scripts/server/audit_paper_boundary.py \
  --database "$ROOT/artifacts/elanquant.sqlite3" \
  --compare "$BEFORE" \
  --out "$AFTER"

echo "official demo corrected opened 2026 diagnostic PASS"
