---
schema_version: 1
mode: auto
project_kind: greenfield
stage: reviewing
current_workflow: byte-review
next_workflow: byte-review
review_verdict: not_ship_external_gates
iteration_count: 3
harness_status: ready
hard_blocked: false
updated_at: 2026-08-13T15:27:00+08:00
---

# Current State

Small r2 remains the sealed live release. Base four-stage training and the
sealed three-cell matrix passed an independent 78/78 receipt audit; an earlier
follower failed only because it used a nonexistent upstream path, so a new
durable service is evaluating the existing matrix without retraining or
promotion. The third product iteration is deployed: the live database was
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

- Base smoke/formal/catalog is still running. Until its immutable receipts pass,
  the UI must not present Base as completed evidence.
- The migrated historical paper ledger is truthfully marked
  `LEGACY_MIXED_RUNS`; it must remain visible and must never be silently rewritten.

## Harness

Server passes 73 pytest tests, Ruff, compileall, shell syntax and systemd unit
verification. Frontend passes 12 Vitest tests, ESLint, TypeScript/Vite build and
npm audit with zero vulnerabilities. Live DB reports `integrity_check=ok` and
zero foreign-key violations. Official release audit, same-session frozen-ledger
comparison and deployed 1440/390 browser QA pass. Only the still-running Base
formal/catalog audit and final delivery review remain.

## Next

Wait for the isolated Base evaluation service, validate its formal receipt and
cross-size six-cell catalog without promoting it over Small. Then complete the
final independent delivery review, delivery ledger and Git push.
