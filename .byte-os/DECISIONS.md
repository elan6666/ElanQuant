# Decision Log

## 2026-08-12 — Independent repository

ElanQuant is developed in its own repository. Existing seven-model results and
its `.byte-os` state are read-only references unless a plan names a reusable
contract explicitly.

## 2026-08-12 — Research and simulation only

The MVP has no real brokerage connection and submits no real order. A broker
gateway interface may be documented, but credentials, API integration, and
automated execution are out of scope.

## 2026-08-12 — Manual trigger

The MVP has no daily scheduler. The owner connects through SMBU VPN/SSH,
presses `Update data and run inference`, and can disconnect after the durable
server job is accepted.

## 2026-08-12 — Server-only research workload

All downloads, dataset materialization, training, inference, backtesting,
paper-ledger generation, and result generation run under
`/data/yilangliu/a_share_research/elanquant`. The Mac holds source and small
copied-back reports only.

## 2026-08-12 — Initial model matrix

Small and Base are both evaluated. Strict PIT is a data/training/evaluation
contract applied to both sizes, not a third architecture.

## 2026-08-13 — Small-first scope

The owner narrowed the current delivery to Kronos Small only. The admitted
matrix is Small zero-shot, Small official-style fine-tune, and Small strict-PIT
fine-tune. Base training and Base production inference are deferred; Base code
or downloaded official weights do not constitute an admitted result.

## Assumptions to verify

- The official Small/Base tokenizer pairing and fine-tune defaults remain
  current in the pinned upstream repository.
- Server data access can extend the daily PIT dataset through the latest closed
  session with sufficient Amount coverage.
- One server GPU can complete the selected fine-tunes within the available Auto
  runtime; otherwise terminal resumable receipts must preserve progress.

## 2026-08-13 — Base comparison reactivated

The owner subsequently authorized the exact Base three-cell experiment on the
same admitted data and official-aligned protocol. Base is a comparison track,
not an automatic production promotion; the Small strict-PIT release remains
the online model until a separate evidence-backed decision changes it.

## 2026-08-13 — Evidence-chain product wave

Patterns from Qlib, MLflow, Evidently, vn.py, QuantStats and related high-quality
repositories are adapted as small native features: split-aware experiments,
run diff, data health, signal explanation and sample-aware paper summaries.
No third-party runtime or broker surface is embedded.

## 2026-08-13 — One paper publication per signal session

The first successful run for a signal session freezes the only paper
publication. A forced same-session rerun may publish new research evidence but
must not add, remove or replace paper intents. Historical mixed-run provenance
is preserved and labelled rather than silently rewritten.

## 2026-08-13 — Preserve Top3 and add an isolated official-demo method version

The existing manual Top3 strict-PIT ranking and paper ledger remain the online
product. A separate historical research version reproduces the pinned Kronos
demo method with standardized-space signals, sample count five and Qlib
Top50/Drop5/minimum-hold-five. It is immutable-artifact and GET-only: it never
writes jobs, inference runs, recommendations, orders, fills, positions or NAV.
Because the admitted extended 2025 validation split, dynamic PIT membership,
provider data, pinned pyqlib version and deterministic seed differ from the
author environment, the product calls it method-aligned rather than an exact
data reproduction and lists every deviation in its receipt and UI.

## 2026-08-13 — Historical Top3 is a post-hoc Qlib sensitivity variant

Add `Top3/Drop1/Hold5` beside the existing Top50/Drop5/Hold5 historical
baseline. Drop1 is the smallest effective Qlib replacement rate and Hold5 keeps
the official holding constraint. The variant reuses exact sealed signals and
providers, is permanently non-selection/non-promotion, and is not equivalent to
the online Top3 paper account. Qlib trading constraints may make actual holdings
temporarily differ from the nominal target of three.

## 2026-08-14 — Official-date-aligned model reset

The active replacement experiment uses the pinned Kronos demo raw slices:
train 2011-01-01..2022-12-31, validation 2022-09-01..2024-06-30, rolling test
2024-04-01..a frozen latest close and backtest 2024-07-01..that same freeze.
Raw overlap supplies lookback context and must not be interpreted as overlapping
labels. The training Dataset consumes 90 context + 10 target + 1 row, runs all
30 epochs and selects best checkpoints by validation loss.

## 2026-08-14 — Viewed rolling test and shared strategy signal

Only anchors whose complete ten-session target is available enter IC/RankIC.
Latest online signals may be published before their targets mature but remain
unscoreable. Once results are inspected the rolling test is TEST_VIEWED and may
not drive model, primary-signal or strategy-parameter changes. Official Top50
50/5/Hold5 and the explicit Top3 3/1/Hold5 extension consume the same
sample-count-five standardized-space mean signal.

## 2026-08-14 — Retire, do not erase, superseded evidence

The old strict-PIT release is removed from the future public selection surface
only after the new official-style replacement passes. Its checkpoints,
receipts, database lineage and historical artifacts remain read-only and are
labelled RETIRED_SUPERSEDED; physical deletion is not authorized.

## 2026-08-14 — Execution profile is not model identity

Local Apple Silicon and remote Linux/NVIDIA are execution profiles for the same
sealed model evidence. Small is the local default and Base is explicit opt-in.
Public configuration never contains the owner's campus host, VPN, username,
token or absolute server paths.
