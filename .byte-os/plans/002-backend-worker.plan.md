---
id: 002
title: Durable backend and paper workflow
status: complete
wave: 2
updated_at: 2026-08-12T16:48:00Z
owner_role: Backend Engineer
depends_on: ['001']
start_directory: backend
context_files: [../AGENTS.md, ../.byte-os/TECH_SPEC.md]
agents_context_stack: [AGENTS.md]
subagent_policy: implementation_allowed
---

# Goal

Deliver loopback API, durable idempotent jobs, worker stages, results, and a
strict frozen-intent simulated account.

# OKR Link

KR3 and KR4.

# Scope

`backend/`, backend tests, service templates.

# Non-Goals

No scheduler, training endpoint, public auth system, or broker.

# Steps

## Step 1: Implement API and queue
- Purpose: durable manual trigger.
- Actions: health/status, 202 submit, list/detail/retry, atomic claim/events.
- Files or modules: backend API/orchestration/storage.
- Expected output: jobs survive request lifecycle and duplicates coalesce.
- Step verification: API/queue tests.
- Subagent: implementation_allowed

## Step 2: Implement research-result and paper APIs
- Purpose: close the owner workflow.
- Actions: runs/scores, frozen T intents, T+1 fill/reject, atomic account ledger.
- Files or modules: pipelines/API/contracts.
- Expected output: reconciling account and fail-closed results.
- Step verification: leakage and ledger tests.
- Subagent: implementation_allowed

## Step 3: Add service deployment
- Purpose: survive disconnect.
- Actions: systemd user templates and operator entrypoints.
- Files or modules: `deploy/`, `scripts/`.
- Expected output: API/worker independently managed.
- Step verification: service syntax and disconnect E2E on server.
- Subagent: none

# Dependencies

001.

# Scoped Commands
- Test: `python -m pytest -q`
- Lint: `ruff check backend scripts tests`
- Typecheck: `pyright backend scripts`
- Build: `python -m compileall -q backend scripts tests`

# AGENTS.md Context
- Root context: `AGENTS.md`
- Module context: none
- Scoped command source: root harness
- Safe edit boundaries: backend/deploy/backend tests
- Missing or stale AGENTS.md notes: none

# Subagent Plan
- Implementation subagent: backend-only.
- Review subagent: read-only security/ledger.
- Isolation boundaries: no frontend/config ownership.
- Merge or handoff notes: main agent integrates research commands.

# Code Change Guardrails

SQLite WAL and polling only; explicit state machine; atomic writes.

# Acceptance Criteria

202 immediate, duplicate coalescing, independent worker, correct paper ledger.

# Verification

Unit/integration plus server disconnect/reconnect.

# Experiment Or Measurement

Submit latency and duplicate count.

# Risks

systemd user linger unavailable.
