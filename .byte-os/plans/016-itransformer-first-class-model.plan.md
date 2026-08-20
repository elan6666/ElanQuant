---
id: 016
title: iTransformer B2 first-class research model surface
status: complete
wave: 1
updated_at: 2026-08-20T12:10:00Z
owner_role: Root Integrator
depends_on: [015]
start_directory: .
context_files: [AGENTS.md, CLAUDE.md, .byte-os/CODEBASE_MAP.md, .byte-os/HARNESS.md]
agents_context_stack: [AGENTS.md]
subagent_policy: implementation_allowed
---

# Goal

Make the sealed CSI300 strict-weekly iTransformer B2 evidence a first-class,
model-selectable ElanQuant research surface alongside Kronos without changing
the existing Kronos online/paper or Qlib historical contracts.

# OKR Link

New KR: the product shows model-family-specific evidence, cadence and ranking
snapshots without mixing daily Kronos and weekly B2 semantics.

# Scope

- Extend the sealed unified-comparison reader with hash-checked weekly ranking
  snapshots sourced from each model's score artifact.
- Add a model-specific read-only ranking endpoint; it exposes the score date,
  frequency, lookback, checkpoint and definition with no SQLite writes.
- Surface the imported B2 model in Jobs, Experiment Matrix, Historical Backtest
  and Stock Ranking as a sealed weekly research model.
- Preserve the existing current-day Kronos ranking and all historical Qlib APIs.

# Non-Goals

- No B2 retraining, no fresh data materialisation, no inference job, no paper
  publication, no order generation and no rewriting immutable B2 artifacts.
- No claim that a 2026-07-24 B2 snapshot is a current daily signal.

# Steps

## Step 1: Extend sealed comparison loading

- Purpose: derive a model-specific snapshot only after the evidence prediction
  CSV has passed its receipt hash and strict schema checks.
- Actions: add a bounded CSV parser, accepted model/anchor validation and a
  GET-only comparison-ranking endpoint.
- Files or modules: `backend/src/elanquant/api/app.py`, backend API tests.
- Expected output: B2 and Kronos Base weekly ranks can be read by model/as-of.
- Step verification: happy path plus unknown model/date, duplicate row and hash
  mismatch tests; ensure no database write occurs.
- Subagent: implementation_allowed.

## Step 2: Add a family-aware UI layer

- Purpose: show B2 everywhere research evidence is selected, while keeping its
  weekly provenance visibly distinct from current Kronos data.
- Actions: add comparison summaries to Jobs/Experiment Matrix, model/ranking
  selectors and clear as-of/frequency wording; retain existing Kronos views.
- Files or modules: `frontend/src/{App.tsx,api.ts,types.ts,pages/*,components/*,styles.css}`, tests.
- Expected output: users can select B2 weekly and Kronos weekly snapshots,
  while the existing live Kronos rank remains available.
- Step verification: frontend parser/component tests, lint and production build.
- Subagent: implementation_allowed.

## Step 3: Verify boundaries and deploy

- Purpose: prove that addition is artifact-only and does not touch paper data.
- Actions: run API/frontend gates, snapshot database logical hashes before and
  after GET calls, build frontend, deploy server source/dist and verify live
  endpoints through the SSH tunnel.
- Files or modules: deployment source/dist and `.byte-os` logs only.
- Expected output: live website with a read-only B2 selector.
- Step verification: server tests/lint/type/compile, frontend tests/lint/build,
  live GET and no paper-table mutation.
- Subagent: none.

# Dependencies

Existing sealed unified comparison catalog r7 and its six receipts.

# Scoped Commands

- Backend: `app-venv/bin/python -m pytest -q`, `app-venv/bin/ruff check backend/src tests`.
- Frontend: `npm --prefix frontend test -- --run`, `npm --prefix frontend run lint`, `npm --prefix frontend run build`.

# Code Change Guardrails

- Keep the original Kronos historical matrix parser exact and independent.
- B2 only reads receipt-bound artifact paths below the existing comparison root.
- Every weekly view labels its latest sealed as-of and avoids "today" wording.

# Acceptance Criteria

1. B2 appears as a model, not as a Kronos size/track.
2. B2 and Kronos weekly rankings come only from hash-verified score artifacts.
3. A weekly B2 selection displays its 80-session lookback and 2026-07-24 as-of.
4. Old live Kronos ranking, paper account and historical Qlib pages remain valid.
5. No GET call writes SQLite rows; all test/build gates pass.

# Risks

The B2 checkpoint's newest admissible evidence ends on 2026-07-24.  A future
weekly refresh requires a separately admitted D0/calendar/snapshot pipeline;
this plan does not fabricate it.
