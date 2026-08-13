---
schema_version: 1
mode: auto
project_kind: greenfield
stage: delivered
current_workflow: byte-deliver
next_workflow: none
review_verdict: ship
iteration_count: 3
harness_status: ready
hard_blocked: false
updated_at: 2026-08-13T20:40:00+08:00
---

# Current State

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

Deliver an auditable Top50-versus-historical-Top3 comparison across the existing
2025/2026 historical evidence, with immutable server receipts, a clear read-only
UI and no change to online Top3 or real brokerage boundaries.

## Open blockers

None. Top3/Drop1/Hold5 is frozen as a post-hoc sensitivity variant. Research
execution is server-only and must not overwrite existing artifacts or use the
opened result for selection.

## Harness

Server passes 97 pytest tests, Ruff, Pyright, compileall, shell syntax and systemd unit
verification. Frontend passes 17 Vitest tests, ESLint, TypeScript/Vite build and
npm audit with zero vulnerabilities. Live DB reports `integrity_check=ok` and
zero foreign-key violations. Official release audit, same-session frozen-ledger
comparison and deployed 1440/390 browser QA pass. Independent design, product,
Base formal and six-cell catalog reviews are SHIP with no P0/P1.

## Next

No required work remains. Future untouched data is reserved for a genuinely
new evaluation rather than tuning against the opened 2026 window.
