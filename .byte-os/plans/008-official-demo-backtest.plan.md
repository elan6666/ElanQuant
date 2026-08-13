---
id: 008
title: Isolated official-demo method historical backtest
status: complete
wave: 5
updated_at: 2026-08-13T15:32:00+08:00
owner_role: Research and Product Engineer
depends_on: ['004', '007']
start_directory: .
context_files: [AGENTS.md, docs/RESEARCH_PROTOCOL.md, .byte-os/TECH_SPEC.md]
agents_context_stack: [AGENTS.md]
subagent_policy: read_only_review
---

# Plan 008 — Official Demo Method Backtest

## Objective

Keep the existing `live_paper_top3_v1` product unchanged and add a separate,
GET-only historical research version aligned to the pinned Kronos Qlib demo:
standardized-space signals, five forecast samples, Top-50, Drop-5 and minimum
hold five.

## Invariants

- Never write or reuse jobs, inference runs, recommendations, paper accounts,
  positions, orders, fills or NAV for the new track.
- The manual update/infer button continues to run only the admitted Small strict
  PIT Top-3 pipeline.
- Use `validation_2025` only; 2026 TEST_VIEWED evidence is not consumed for
  selection.
- Missing or malformed artifacts render an unavailable state or HTTP 503; no
  mock success path.

## Work

1. Seal standardized Small official-ft signals using the pinned low-level
   Kronos inference path and four official close-difference formulas.
2. Build an admitted read-only Qlib provider and pin pyqlib 0.9.7 identities.
3. Run all four signals through TopkDropout 50/5/hold5 with the author demo's
   execution, benchmark and fee constants.
4. Publish an immutable receipt plus historical-backtest catalog.
5. Add fail-closed GET endpoints and a dedicated `历史回测` page that visibly
   separates the new research track from Top3 paper trading.
6. Verify paper tables are byte-for-byte unchanged, complete server/frontend
   tests, desktop/mobile QA and independent review.

## Status

Complete. The immutable signal receipt contains 67,349 rows across 233
cross-sections. The pinned pyqlib 0.9.7 Top50/Drop5/Hold5 backtest and catalog
are sealed, the fail-closed GET API and dedicated page are deployed, and an
independent release audit confirms every pre-existing Top3 paper table remained
unchanged. Desktop/mobile QA and all backend/frontend gates pass.
