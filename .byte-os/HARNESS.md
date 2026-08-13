# Codebase Harness

- Reviewed: 2026-08-13
- Repository kind: greenfield
- Claude support: ready
- Codex support: ready
- Root context: `CLAUDE.md`, `AGENTS.md`
- Codebase map: ready
- Scoped command matrix: verified on the server and frontend runtime
- Noise filters: `.gitignore` and `.claude/settings.json`
- LSP guidance: Pyright and tsserver
- Subagent exploration/implementation: Base research, PIT/ledger and product
  architecture tracks completed with a final read-only static review
- AGENTS.md quality: ready and pointer-oriented

## Current command evidence

- Server full suite: 97 pytest PASS, Ruff PASS, Pyright 0 errors/warnings,
  compileall PASS, all shell syntax PASS and both systemd units verify.
- Frontend: 17 Vitest PASS, ESLint PASS, TypeScript/Vite build PASS and
  `npm audit --omit=dev` reports zero vulnerabilities.
- Browser: deployed data-bearing pages at 1440 × 1000 and 390 × 844 have zero
  console warnings/errors and no page overflow. Mobile heading wrapping was
  corrected from the first visual pass and rechecked live.
- Official-demo release audit: 67,349 standardized signal rows, 233 sessions,
  canonical catalog receipt PASS and all Top3 paper tables unchanged.
- Historical 2×2 catalog: Top50/Top3 across 2025/2026, all 740 curve-session
  and holdings-session identities available, canonical audit PASS and SQLite
  logical table hashes unchanged.
- Same-session Top3 force refresh: 900 scores, six split-evaluation rows,
  `SKIPPED_EXISTING_FROZEN_RUN`, and frozen ledger hash unchanged.
- Research runtime: PyTorch 2.7.1+cu128 with two RTX 5090; isolated target deps.
- Module-local AGENTS.md files remain unnecessary at current size.
