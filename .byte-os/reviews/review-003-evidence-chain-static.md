# Review 003 — Evidence-chain static gate

Date: 2026-08-13

## Scope

Read-only review of the Small/Base research catalog, database migration, paper
publication invariant, run provenance/diff and Claude-warm frontend. No server
POST, training mutation or live database write was made by the reviewer.

## Findings resolved during the iteration

- Historical recommendation days with zero orders are now frozen to their first
  source run; a later-only order source is labelled `LEGACY_MIXED_RUNS` without
  rewriting history.
- Frozen buys reserve known commission and execute by recommendation rank.
- Paper publication rereads verified snapshot bytes and rejects TOCTOU changes.
- The catalog is fail-closed at both producer and API consumer; the frontend
  treats a catalog 503 as optional research evidence rather than a control-plane
  outage.
- Empty strict-PIT coverage cannot produce a fake comparable run diff.
- Data/model/tokenizer/config/code/evaluation hashes and identity/rank changes
  are visible.
- The warm accent now clears WCAG AA contrast for normal text.

## Verification

- Local non-API: 42 pytest PASS; Ruff, compileall and `git diff --check` PASS.
- Frontend: 10 Vitest PASS; ESLint, TypeScript/Vite build and npm audit PASS.
- Independent verdict: **SHIP-for-static**, with no remaining P0/P1.

## External gates

Final overall SHIP still requires renewed interactive SSH authentication, Base
terminal/formal/catalog audit, full server pytest/Pyright, live SQLite backup
and migration, one safe same-session evidence refresh, deployed desktop/mobile
QA and Git delivery.
