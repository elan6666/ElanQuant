---
schema_version: 1
mode: auto
project_kind: greenfield
stage: delivered
current_workflow: byte-deliver
next_workflow: complete
review_verdict: ship
iteration_count: 3
harness_status: ready
hard_blocked: false
updated_at: 2026-08-13T15:55:00+08:00
---

# Current State

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

Deliver an auditable A-share Kronos Small/Base comparison and strict-PIT
research/simulated-trading web system with server training and on-demand
inference, without real brokerage connectivity.

## Open blockers

None. The migrated historical paper ledger remains truthfully marked
`LEGACY_MIXED_RUNS`; this is preserved provenance, not an unfinished gate.

## Harness

Server passes 75 pytest tests, Ruff, Pyright, compileall, shell syntax and systemd unit
verification. Frontend passes 12 Vitest tests, ESLint, TypeScript/Vite build and
npm audit with zero vulnerabilities. Live DB reports `integrity_check=ok` and
zero foreign-key violations. Official release audit, same-session frozen-ledger
comparison and deployed 1440/390 browser QA pass. Independent design, product,
Base formal and six-cell catalog reviews are SHIP with no P0/P1.

## Next

Use the manual Top3 button as before; inspect Base only as research evidence and
the new Top50 historical method version on the dedicated page. No real broker,
automatic schedule or Base promotion is enabled.
