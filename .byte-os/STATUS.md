---
schema_version: 1
mode: auto
project_kind: existing_codebase
stage: building
current_workflow: byte-build
next_workflow: byte-build
review_verdict: pending
iteration_count: 0
harness_status: ready
hard_blocked: false
updated_at: 2026-08-14T23:36:00+08:00
---

# Current State

Byte Auto has resumed with an owner-approved model/data reset and portability
goal. The active target is Small/Base zero-shot plus newly trained official-style
fine-tunes using the pinned Kronos raw slices: train 2011-01-01..2022-12-31,
validation 2022-09-01..2024-06-30, rolling test 2024-04-01..a frozen latest
closed session, and backtest 2024-07-01..that same freeze. Top50/Drop5/Hold5 and
Top3/Drop1/Hold5 must consume the same sample-count-five standardized-space
signals. The rolling test is permanently labelled viewed after publication;
only anchors with a matured ten-session target enter IC/RankIC metrics.

The official-split compatibility release is now active. Public selectors expose
exactly Small/Base × zero-shot/official-ft; old strict-PIT checkpoints and
receipts remain preserved as retired evidence and are not physically deleted.

The same model evidence must run under two execution profiles: local Apple
Silicon (Small default, Base explicit high-resource option) and a configurable
remote Linux/NVIDIA server. Public reproduction must provide official-weight
download receipts, BYO CSV/Parquet import, optional user-owned Tushare adapter,
device preflight/smoke tests and a concise README without exposing the owner's
server, VPN, token, raw data or generated artifacts.

Plan 010 is complete: both sealed Top50 historical tracks now sit beside an
isolated Qlib historical Top3/Drop1/Hold5 portfolio-sensitivity variant for
2025 and corrected opened 2026. The exact four cells include hash-bound daily
holdings and a read-only session viewer. They reuse existing signal/provider
bytes, never run inference, never write SQLite, and never claim equivalence
with the online Top3 paper account.

Plan 009 is complete. The historical SVG no longer clips its curve, 2025 is
truthfully identified as training validation and best-checkpoint selection, and
the active second view is a corrected 2026 opened out-of-sample diagnostic.
The first future-support-conditioned 2026 artifact is preserved but excluded
from the active catalog. A future untouched window is reserved for the next
true final test.

Small r2 remains the sealed live release. Base four-stage training and the
sealed three-cell matrix, formal evaluation and six-cell catalog have passed
independent receipt audits without retraining or promotion. The third product
iteration is deployed: the live database was
backed up, migrated by one process, checked for integrity and restarted with the
six-cell evidence catalog, run/data/stock lineage, sample-aware paper accounting
and Claude-inspired warm editorial dashboard.
The existing Top3 track remains unchanged. Plan 008's completely isolated
official-demo-method historical version is now sealed and deployed: 67,349
standardized signal rows, 233 sessions, Top50/Drop5/Hold5, GET-only API and a
dedicated page. Its independent audit proves every Top3 paper table was
unchanged. A same-session Top3 force refresh also left the frozen ledger
unchanged while publishing current run evidence.

## Goal

Deliver a reproducible ElanQuant reset with official-date-aligned Small/Base
fine-tuning, mature rolling-test evaluation, Top50 and Top3 historical studies,
local/remote inference profiles, third-party bootstrap/data/weight workflows,
and a simpler evidence-led web product while preserving the no-broker boundary.

## Current build evidence

Official-split-v3 raw data, causal materialization and admission are PASS. Small
and Base Tokenizer/Predictor training completed 30 epochs with fresh, sealed
terminal receipts. The exact four-cell matrix, pre-result analysis and online
method locks, four-model rolling evaluation and eight Top50/Top3 backtests are
sealed. `releases/current` points to
`kronos-official-split-v3-causal-r4-20260814-compat-v3`.

The compatibility layer preserves the predeclared online runner byte-for-byte,
adapts only `vol/amt` to its required `volume/amount` schema, and adds a
byte-identical `formal-evaluation.json` alias without changing the original
candidate release. The compatibility receipt records that it was applied after
viewed results and is not selection or performance-promotion evidence.

Live Small and Base force E2E runs both succeeded on the remote CUDA profile.
Small published 600 scores and one frozen Top3 recommendation set; Base
published 600 research-only scores and changed none of the paper,
recommendation, order, position, fill, valuation or portfolio tables. The live
status reports `small-official-ft` as the primary model and 2026-08-14 as the
latest closed/data/inference session.

Portable execution is implemented and verified on both target profiles:
Apple Silicon reports PyTorch 2.13/MPS PASS and the Linux server reports
PyTorch 2.13+cu130/RTX 5090 CUDA PASS. Both synthetic smoke receipts are finite
and explicitly non-model tests. A clean wheel/sdist build contains no data,
weights, checkpoint, database or token files; a fresh Python 3.12 wheel install
successfully imports the bundled synthetic CSV and runs bootstrap dry-run.

The official-v3 API/frontend adapter reads exact four-model evaluation and eight
historical entries, including sealed series and holdings. Frontend 26 tests,
ESLint, build and zero-vulnerability audit PASS; server 155 tests (one skipped),
Ruff, compileall and Pyright PASS.

## Open blockers

No current product/runtime blocker. Public redistribution of newly fine-tuned
A-share weights remains gated on data-license evidence; this does not block the
source, official-weight downloader or BYO-data reproduction recipe. Rolling
test and backtest results are viewed, non-selection research evidence and are
not investment-performance promotion evidence.

## Harness

Server passes 155 pytest tests (one skipped), Ruff, Pyright and compileall.
Frontend passes 26 Vitest tests, ESLint, TypeScript/Vite build and npm audit with
zero vulnerabilities. API and Worker are active on loopback; hostile Host is
rejected; the live DB reports `integrity_check=ok` and zero foreign-key
violations. The compatibility release and its full dependency chain are sealed
read-only and independently audited with no P0/P1.

## Next

Complete final Safari 1440/390 visual QA after the Mac is unlocked, then commit
the reviewed compatibility/runtime delivery locally. Do not push unless the
owner explicitly activates publication.
