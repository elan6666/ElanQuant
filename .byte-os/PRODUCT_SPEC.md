# Product Specification — ElanQuant v1

## Positioning

ElanQuant is a reproducible, research-only A-share Kronos system. It trains and
compares Small/Base against the pinned author's A-share demo date slices,
separates model evaluation from portfolio backtesting, and runs the same sealed
model evidence on either Apple Silicon or a user-owned Linux/NVIDIA server.

## Target users

- Primary: the owner learning full-stack engineering and quantitative research.
- Secondary: a technical user reproducing the workflow with their own licensed data.
- Reviewer: an auditor checking split, model, execution and result receipts.

## Core jobs

1. Prepare admitted A-share OHLCVA data without committing or redistributing it.
2. Download and verify official Kronos Tokenizer/Small/Base weights.
3. Reproduce official-date-aligned Small/Base fine-tuning and best-checkpoint selection.
4. Evaluate only matured rolling-test labels, then compare Top50 and Top3 backtests.
5. Run admitted inference locally or remotely without changing model identity.
6. Understand every percentage, rank and metric shown in the web product.

## Active model matrix

- `small-zero-shot`
- `small-official-ft-v1`
- `base-zero-shot`
- `base-official-ft-v1`

Strict-PIT is retired from active selectors. Existing strict-PIT releases,
receipts and database lineage remain read-only as `RETIRED_SUPERSEDED` evidence.

## Imported weekly research model

- `itransformer-r16g-r3-b2` is a separate CSI300 strict-weekly research model,
  not a Kronos variant.  It uses 80 observed past sessions of open-to-open log
  returns and a weekly holding-period target.
- Its displayed 2026-07-24 ranking is a sealed viewed-research snapshot.  It
  is selectable in research views, but is not a current daily ranking, paper
  model or promotion candidate.
- The separately evaluated public `kronos-base-zero-shot` weekly snapshot
  shares the B2 anchors/execution only for controlled cross-model comparison;
  it retains its 90-session OHLCVA input contract.

## Data and evaluation contract

- Raw train slice: 2011-01-01..2022-12-31.
- Raw validation slice: 2022-09-01..2024-06-30.
- Raw rolling-test slice: 2024-04-01..frozen latest closed session.
- Requested backtest window: 2024-07-01..the same frozen session.
- Training samples consume 90 context + 10 prediction + 1 row.
- Effective context/anchor/target/consumed ranges are computed and proven; raw
  lookback overlap is not mislabeled as label overlap.
- Validation selects best checkpoints. Rolling test is `TEST_VIEWED` after
  publication and cannot select models, signals or portfolio parameters.
- IC/RankIC use only anchors with ten realized future exchange sessions.
- Latest online predictions remain unscoreable until their targets mature.

## Historical strategies

- Official baseline: Top50/Drop5/Hold5.
- Portfolio-size extension: Top3/Drop1/Hold5.
- Both consume the exact same model predictions, sample_count=5 and
  standardized-space mean signal. Last/max/min remain diagnostics only.
- Requested and actual first signal/execution dates are both published.

## Execution profiles

- `local-apple-silicon`: Small default; Base explicit high-memory opt-in; MPS or
  CPU is resolved explicitly and never silently substituted.
- `remote-linux-nvidia`: Small default; Base opt-in; CUDA admission required.
- `legacy-yilangliu`: private compatible deployment profile, absent from public defaults.

Execution profile is not model identity. Every run binds model-evidence,
execution, data and code identities separately.

## Reproduction surface

- Five-minute synthetic UI/contract demo.
- Official-weight zero-shot inference using verified pinned downloads.
- BYO CSV/Parquet or optional user-owned Tushare adapter.
- Full Small/Base official-style fine-tuning, rolling evaluation and backtesting.
- Bootstrap, doctor, smoke and weight verify commands with immutable receipts.

## Non-goals

- Real brokerage connectivity, real orders or investment advice.
- Redistributing Tushare/raw provider data or user credentials.
- Publishing ElanQuant fine-tuned weights without a positive data-license gate.
- Claiming the rolling viewed test is an untouched final test.
- Treating Top3 as an official Kronos parameter or local/remote as different models.
- Training on Apple Silicon in v1.

## Acceptance criteria

1. Four active model cells have sealed identities and exact split receipts.
2. Small/Base official-style training completes 30 epochs and seals best checkpoints.
3. Mature rolling evaluation and both historical strategies publish fail-closed receipts.
4. Local Small and remote Small/Base smoke gates publish execution receipts; no fallback.
5. CSV/Parquet import and official-weight fetch/verify are reproducible and secret-safe.
6. Public UI exposes four cells only, removes Methods and explains derived metrics.
7. Existing strict-PIT evidence remains readable but cannot be selected as active.
8. Backend/frontend/package/server/browser/security gates pass and delivery is Git-clean.
