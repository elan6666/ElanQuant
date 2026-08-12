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
