# Codebase Harness

- Reviewed: 2026-08-12
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

- Local non-API evidence suite: 42 pytest PASS, Ruff PASS, compileall PASS and
  `git diff --check` PASS. Full API suite remains server-only.
- Frontend: 10 Vitest PASS, ESLint PASS, TypeScript/Vite build PASS and
  `npm audit --omit=dev` reports zero vulnerabilities.
- Browser: current error-state shell at 1440px and emulated 390px has zero
  console errors and no page overflow; final data-bearing live QA waits for deploy.
- Research runtime: PyTorch 2.7.1+cu128 with two RTX 5090; isolated target deps.
- Module-local AGENTS.md files remain unnecessary at current size.
