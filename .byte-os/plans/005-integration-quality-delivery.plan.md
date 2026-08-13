---
id: 005
title: Integration, quality, operations and delivery
status: complete
wave: 3
updated_at: 2026-08-13T15:55:00+08:00
owner_role: QA Engineer
depends_on: ['002', '003', '004']
start_directory: .
context_files: [AGENTS.md, .byte-os/PRODUCT_SPEC.md, .byte-os/TECH_SPEC.md]
agents_context_stack: [AGENTS.md]
subagent_policy: read_only_exploration
---

# Goal

Integrate the live server workflow, review, iterate three times, and deliver.

# OKR Link

All KRs.

# Scope

Integration tests, docs, service setup, browser QA, review/iterations/delivery.

# Non-Goals

No real broker or scope expansion.

# Steps

## Step 1: Integrate and dogfood
- Purpose: prove first workflow.
- Actions: deploy loopback services, tunnel, submit, disconnect, reconnect,
  inspect research/ranking/paper account.
- Files or modules: deploy/docs/integration tests.
- Expected output: recorded E2E evidence.
- Step verification: live server and browser.
- Subagent: none

## Step 2: Review and three iterations
- Purpose: meet Auto quality contract.
- Actions: current review; completeness, UX, and delivery-readiness iterations;
  fresh verification/review.
- Files or modules: source/tests/docs/Byte OS evidence.
- Expected output: three iteration records and ship verdict.
- Step verification: full command matrix and acceptance audit.
- Subagent: read_only_exploration

## Step 3: Package delivery
- Purpose: durable handoff.
- Actions: README/operator/learning guides, delivery state, Git cleanliness.
- Files or modules: docs, README, `.byte-os/DELIVERY.md`.
- Expected output: usable owner handoff.
- Step verification: fresh clone/install instructions and no restricted files.
- Subagent: none

# Dependencies

002, 003, 004.

# Scoped Commands
- Test: backend + frontend + server + E2E
- Lint: backend/frontend
- Typecheck: backend/frontend
- Build: production frontend and service smoke

# AGENTS.md Context
- Root context: `AGENTS.md`
- Module context: none
- Scoped command source: harness
- Safe edit boundaries: new repo only
- Missing or stale AGENTS.md notes: reconcile commands at delivery

# Subagent Plan
- Review agents: read-only PIT/security/UX and delivery.
- Merge or handoff notes: root owns fixes and final verdict.

# Code Change Guardrails

Evidence-led fixes only; no late speculative features.

# Acceptance Criteria

All v0 plans complete, three iterations, current ship review, delivery exists.

# Verification

All commands and live owner flow.

# Experiment Or Measurement

Core flow completion and zero critical review findings.

# Risks

Long training runtime or service permissions may require resumable terminal state.
