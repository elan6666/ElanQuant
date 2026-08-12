---
id: 003
title: Owner dashboard
status: complete
wave: 2
updated_at: 2026-08-12T16:48:00Z
owner_role: Frontend Engineer
depends_on: ['001']
start_directory: frontend
context_files: [../AGENTS.md, ../.byte-os/UX_SPEC.md]
agents_context_stack: [AGENTS.md]
subagent_policy: implementation_allowed
---

# Goal

Build a responsive Chinese dashboard for the entire first workflow.

# OKR Link

KR3 and KR4.

# Scope

`frontend/` only.

# Non-Goals

No browser compute, training control, broker control, or WebSockets.

# Steps

## Step 1: Build shell and typed API
- Purpose: safe fail-closed owner UI.
- Actions: navigation, polling client/types, risk notice, first-run help.
- Files or modules: `frontend/src`.
- Expected output: responsive shell and schema errors.
- Step verification: Vitest/build.
- Subagent: implementation_allowed

## Step 2: Build workflow pages
- Purpose: expose evidence and action.
- Actions: overview button, jobs, research matrix, ranking/detail, paper account, methods.
- Files or modules: `frontend/src/pages`, components, styles.
- Expected output: empty/running/failed/success views.
- Step verification: component tests and browser QA.
- Subagent: implementation_allowed

# Dependencies

001.

# Scoped Commands
- Test: `npm test`
- Lint: `npm run lint`
- Typecheck: `npm run build`
- Build: `npm run build`

# AGENTS.md Context
- Root context: `AGENTS.md`
- Module context: none
- Scoped command source: root harness
- Safe edit boundaries: frontend only
- Missing or stale AGENTS.md notes: none

# Subagent Plan
- Implementation subagent: frontend-only.
- Review subagent: browser/UX after integration.
- Isolation boundaries: no backend/root files.
- Merge or handoff notes: main agent validates against live API.

# Code Change Guardrails

Small pages/components; no monolithic static JSON app.

# Acceptance Criteria

Core workflow and all specified states render responsively and accessibly.

# Verification

Vitest, lint, build, desktop/mobile/console browser QA.

# Experiment Or Measurement

Owner can locate primary action and latest status without documentation.

# Risks

Contract drift before backend integration.
