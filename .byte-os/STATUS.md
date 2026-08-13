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
updated_at: 2026-08-13T13:38:00+08:00
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

Server pytest passes 65 tests after a real API-contract fix; server Ruff and
compileall pass. Frontend passes 10 Vitest tests, ESLint, TypeScript/Vite build
and npm audit with zero vulnerabilities. Live DB migration reports
`integrity_check=ok` and zero foreign-key violations. Final Base artifact audit,
same-session evidence refresh, desktop/mobile browser QA and delivery review
remain.

## Next

Wait for the isolated Base evaluation service, validate smoke/formal/catalog,
then run one same-session force evidence refresh after the GPU is free. Confirm
that the frozen historical orders are byte-for-byte unchanged and that the new
run contains data-health plus all Small split evidence. Finish desktop/mobile
Browser QA, final independent review, delivery ledger and Git push.
