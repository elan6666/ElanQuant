---
id: "010"
title: Historical Qlib Top3 sensitivity variant
status: complete
wave: 1
updated_at: 2026-08-13T12:40:00Z
owner_role: root integrator
depends_on: ["009"]
start_directory: .
context_files: [AGENTS.md, CLAUDE.md, .byte-os/CODEBASE_MAP.md, .byte-os/HARNESS.md]
agents_context_stack: [AGENTS.md]
subagent_policy: implementation_allowed
---

# Goal

Add an immutable historical Qlib Top3/Drop1/Hold5 portfolio-sensitivity variant
beside the existing Top50 baseline for both admitted splits, without inference,
SQLite mutation, online-account coupling or result-driven promotion. Seal the
actual evaluation-period holdings and expose them through a read-only session
selector without rewriting the first completed evidence set.

# OKR Link

KR8: exact 2×2 historical matrix with unchanged paper/current-release evidence.

# Scope

- New variant contract, pre-result comparison lock, runner, catalog builder and auditor.
- Existing GET-only API extended to the exact four-cell catalog.
- Claude-warm split/strategy comparison UX and responsive three-line chart.
- Server-only two backtests reusing sealed signals/provider bytes.
- Immutable daily holdings artifact, bounded GET endpoint and holdings viewer.
- Full static/live/audit/deployment/Git delivery.

# Non-Goals

- No model/data rebuild, inference, training, database migration, POST endpoint,
  online Top3 behavior change, broker, schedule, Top50 artifact overwrite or
  interpretation as a blind/final test.

# Steps

## Step 1: Freeze the variant contract before results

- Purpose: prevent result-driven portfolio parameter changes.
- Actions: implement exact Top3/Drop1/Hold5 contract and a comparison lock that
  binds runner/contract/Qlib and both immutable source tracks.
- Files: `backend/src/elanquant/contracts/historical_variants.py`, new server scripts/tests.
- Expected output: canonical lock produced before any Top3 metric.
- Step verification: negative contract tests reject parameter/hash/selection drift.
- Subagent: implementation_allowed.

## Step 2: Generate sealed Top3 evidence

- Purpose: compute only the portfolio sensitivity layer.
- Actions: consume existing signals/providers in independent 2025/2026 processes,
  preserve turnover/raw report, position-count and per-instrument holdings
  evidence, then audit/chmod under a new run identity.
- Files: server ignored `runs/backtests/**`; no Git artifact.
- Expected output: two PASS receipts and daily series.
- Step verification: independent metric/hash/support/paper/current-release audit.
- Subagent: root server integration.

## Step 3: Publish exact four-cell GET catalog

- Purpose: expose complete evidence or fail closed.
- Actions: build immutable catalog v4/schema v3; extend loader/public API without
  database writes or new mutations; add a hash-checked, bounded holdings GET.
- Files: contract module, API/settings/systemd, API tests.
- Expected output: exact unique `(split, variant)` pairs.
- Step verification: missing/extra/tampered/cohort mismatch => failure/503; POST 405.
- Subagent: implementation_allowed.

## Step 4: Add split and strategy comparison UX

- Purpose: make Top50/Top3 comparison clear without confusing online Top3.
- Actions: split switch, two summary cards, three-line chart, selected-strategy
  details, post-hoc labels and responsive/accessibility states.
- Files: `frontend/src/**` and tests.
- Expected output: default 2026, default Top50, explicit Qlib historical Top3.
- Step verification: Vitest/lint/build and 1440/390 browser QA.
- Subagent: implementation_allowed.

## Step 5: Review, iterate and deliver

- Purpose: close statistical, product and deployment risks.
- Actions: three evidence-led iterations, independent current review, deploy
  v4 pointer, prove DB/source/dist integrity, commit and push.
- Files: `.byte-os/`, docs, settings/service environment.
- Expected output: SHIP review and reproducible handoff.
- Step verification: server/frontend/full live gates and Git/source hash equality.
- Subagent: read_only_exploration.

# Dependencies

Step 1 precedes server results; Steps 3/4 may implement in parallel after the
contract shape is frozen; Step 5 follows all evidence.

# Scoped Commands

- Test: `app-venv/bin/python -m pytest -q`
- Lint: `app-venv/bin/ruff check backend/src scripts tests`
- Typecheck: `app-venv/bin/pyright backend/src scripts/research`
- Build: `npm --prefix frontend test -- --run && npm --prefix frontend run lint && npm --prefix frontend run build`

# AGENTS.md Context

- Root context: `AGENTS.md`, parent `/Users/elan/Documents/量化/AGENTS.md`.
- Module context: none required.
- Scoped command source: `AGENTS.md`, `.byte-os/HARNESS.md`.
- Safe boundaries: source/spec only on Mac; research artifacts server-only.
- Missing notes: existing harness metrics are stale and will be refreshed.

# Subagent Plan

- Research/contracts: `base_receipt_audit`, new isolated contract/scripts/tests.
- API: `live_product_review`, API/settings/tests only.
- Frontend: `design_qa_review`, frontend source/tests only.
- Root owns plan/specs, merge, lock creation, server execution, deploy and Git.

# Code Change Guardrails

Additive identities; preserve old receipt bytes and validators; no generic
strategy framework beyond the exact Top50/Top3 matrix; fail closed.

# Acceptance Criteria

1. Exact four historical entries and no partial catalog.
2. Top3 parameters are 3/1/5 and all implicit Qlib defaults/Qlib identity are locked.
3. Source signals/providers are byte-identical; no model/GPU inference runs.
4. Both Top3 cells are post-hoc, non-selection, non-promotion and non-online-equivalent.
5. Top3 daily evidence exposes turnover and actual holding-count limitations.
6. Existing Top50 artifacts, Small release, SQLite and online Top3 are unchanged.
7. API remains GET-only/fail-closed; UI is accessible/responsive and honest.
8. All static/server/live/Git/review gates pass.

# Verification

See scoped commands plus canonical receipt recomputation, paper-table before/
after hashes, `releases/current` hash, Host/405 checks, browser console/layout,
permissions 0440/0550 and local/server/origin checksum equality.

# Experiment Or Measurement

Compare Top50 vs Top3 within each split only; report mean-primary return,
excess, IR, drawdown, turnover and actual position-count distribution. Never
choose a strategy from opened 2026 results.

# Risks

Post-hoc concentration, integer Drop1 scale deviation, non-constant actual
cardinality, opened 2026, and legacy 2025 candidate semantics.
