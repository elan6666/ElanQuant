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
