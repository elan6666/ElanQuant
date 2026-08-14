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
updated_at: 2026-08-14T15:54:00+08:00
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

The old strict-PIT release remains running while the replacement is built, but
is now a retirement candidate rather than an active future product version. It
will be removed from public selectors only after the new official-style release
passes data, training, evaluation, backtest and online smoke gates. Existing
checkpoints and receipts are preserved read-only as superseded evidence; no
physical deletion is authorized.

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

## Open blockers

No current hard blocker. Public redistribution of newly fine-tuned A-share
weights remains gated on data-license evidence; this does not block publishing
the source, official-weight downloader or BYO-data reproduction recipe. Apple
MPS and Base-local labels remain unavailable until device smoke gates pass.

## Harness

Server passes 97 pytest tests, Ruff, Pyright, compileall, shell syntax and systemd unit
verification. Frontend passes 17 Vitest tests, ESLint, TypeScript/Vite build and
npm audit with zero vulnerabilities. Live DB reports `integrity_check=ok` and
zero foreign-key violations. Official release audit, same-session frozen-ledger
comparison and deployed 1440/390 browser QA pass. Independent design, product,
Base formal and six-cell catalog reviews are SHIP with no P0/P1.

## Next

Refresh research/specs and executable plans, implement the portable data and
execution foundation, then start immutable server data materialization and
Small/Base training while frontend, README and local-profile work continue.
