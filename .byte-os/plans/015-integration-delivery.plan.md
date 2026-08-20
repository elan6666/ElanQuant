---
id: 015
title: Integration, migration, review and delivery
status: complete
wave: 2
updated_at: 2026-08-14T07:50:00Z
owner_role: Root Integrator
depends_on: [011, 012, 013, 014]
start_directory: .
context_files: [AGENTS.md, CLAUDE.md, .byte-os/HARNESS.md]
agents_context_stack: [AGENTS.md]
subagent_policy: read_only_exploration
---

# Goal

Integrate reviewed source, complete real server evidence, switch the active
release safely, deploy, iterate three times and deliver a reproducible Git state.

# OKR Link

All KRs.

# Scope

Integration tests, README/docs, migration/deploy, Byte OS reviews/iterations/delivery.

# Non-Goals

No physical artifact deletion, no broker, no checkpoint upload without license gate.

# Steps

## Step 1: Freeze and sync source
- Actions: full local gates, commit/push reviewed source, exact server source hash sync.
- Verification: clean Git, source/dist checksum equality.

## Step 2: Complete and audit real research
- Actions: wait persistent training, formal evaluation, Top50/Top3; independent hash/PIT audit.
- Verification: exact receipts, old release/DB unchanged.

## Step 3: Deploy migration and active release
- Actions: backup DB, single-process migration, atomic release/config switch,
  restart API/worker, real job/disconnect E2E.
- Verification: integrity/FK, GET/POST, GPU release, no secret/log regression.

## Step 4: Three evidence-led iterations
- Actions: completeness, UX/onboarding, quality/delivery reviews and fixes.
- Verification: fresh SHIP review after each required repair.

## Step 5: Deliver
- Actions: final README/package/release notes, Byte OS DELIVERY, goal completion.
- Verification: another technical user can follow commands from zero.

# Acceptance Criteria

All plans complete, real evidence admitted, old evidence retired not erased,
services healthy, browser QA passes, repository clean/pushed and latest review SHIP.
