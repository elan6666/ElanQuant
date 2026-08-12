---
id: 007
title: Evidence-chain product optimization
status: in_progress
wave: 4
updated_at: 2026-08-13T05:10:00+08:00
owner_role: Full-stack Engineer
depends_on: ['002', '003', '004']
start_directory: .
context_files: [AGENTS.md, .byte-os/RESEARCH.md, .byte-os/COMPETITORS.md]
agents_context_stack: [AGENTS.md]
subagent_policy: read_only_review
---

# Goal

Turn the dashboard from a result list into a truthful navigable chain from data
snapshot through experiment and stock signal to the simulated ledger.

# Scope

SQLite evidence summaries and paper-publication invariant; run/data/paper APIs;
six-cell experiment UI; data health, run diff, stock explanation, sample-aware
paper summary; adaptive polling and responsive/keyboard QA.

# Non-Goals

No broker, scheduler, public bind, new external runtime, technical-indicator
wall, fabricated forecast bands, or selection on viewed 2026 evidence.

# Steps

1. Freeze exactly one paper publication per signal session; keep forced reruns
   research-only and expose explicit board-lot/no-order decisions.
2. Persist immutable snapshot and dual-split model evidence inside the atomic
   run publication transaction.
3. Add bounded GET endpoints for runs/diff/data-health/stock evidence and paper
   summary, with fail-closed response decoders.
4. Extend the existing Claude-warm pages with six-cell comparison, data health,
   searchable ranking explanations and evidence-aware paper metrics.
5. Backup/migrate live SQLite with one process, deploy, run full tests and
   desktop/mobile/no-console checks, then request independent review.

# Acceptance Criteria

- A same-session force rerun cannot mutate the first frozen paper publication.
- Dual splits, support, hashes, run differences and data limitations are visible.
- Insufficient paper evidence produces null/explicit state, not fake metrics.
- API/frontend contracts pass and the live DB remains integral after migration.

# Verification

Backend/API/ledger tests, frontend Vitest/ESLint/build/audit, SQLite
integrity/foreign-key checks, live GET E2E and 1440px/390px browser QA.
