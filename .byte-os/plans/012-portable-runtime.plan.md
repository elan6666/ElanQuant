---
id: 012
title: Local and remote execution profiles
status: complete
wave: 1
updated_at: 2026-08-14T10:40:00Z
owner_role: Platform Engineer
depends_on: []
start_directory: backend
context_files: [AGENTS.md, CLAUDE.md, .byte-os/TECH_SPEC.md]
agents_context_stack: [AGENTS.md]
subagent_policy: implementation_allowed
---

# Goal

Run the same sealed release through explicit Apple Silicon or Linux/NVIDIA
execution profiles with no silent device fallback.

# OKR Link

KR3, KR8.

# Scope

Backend runtime/config/job contract, CLI, deploy templates and focused tests.

# Non-Goals

No Apple training, no public server credentials, no automatic remote SSH
orchestration, no model identity changes.

# Steps

## Step 1: Define portable execution receipts
- Purpose: separate model evidence from hardware execution.
- Actions: profile/release/device schemas, capability gate, environment allowlist.
- Files or modules: backend contracts/execution/settings.
- Expected output: canonical execution identity.
- Step verification: unit and tamper tests.
- Subagent: implementation_allowed.

## Step 2: Persist profile through jobs
- Purpose: make submission/retry/idempotency honest.
- Actions: additive DB migration, API/status/POST response fields, claim-before-capability gate.
- Expected output: old jobs map to legacy profile; new jobs freeze profile/release.
- Step verification: API/worker/migration tests.
- Subagent: implementation_allowed.

## Step 3: Add doctor and smoke
- Purpose: admit MPS/CPU/CUDA before real inference.
- Actions: read-only doctor, synthetic smoke, explicit backend resolution and receipts.
- Expected output: Mac Small and remote CUDA evidence or typed unavailable state.
- Step verification: local synthetic smoke, server CUDA smoke, no-secret output scan.
- Subagent: implementation_allowed.

# Acceptance Criteria

No fallback; idempotency includes profile/release; retry inherits profile; private
paths absent from public defaults; old worker remains compatible; Small default/Base opt-in.

# Verification

Full backend pytest/Ruff/Pyright/compile plus synthetic Mac and server smoke receipts.
