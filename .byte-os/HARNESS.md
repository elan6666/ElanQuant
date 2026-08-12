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
- Subagent exploration/implementation: three bounded tracks completed
- AGENTS.md quality: ready and pointer-oriented

## Current command evidence

- Server: 30 pytest PASS, Ruff PASS, Pyright 0 errors, compileall PASS.
- Frontend: 6 Vitest PASS, ESLint PASS, TypeScript/Vite build PASS.
- Browser: 1440px and emulated 390px PASS; zero console errors and no overflow.
- Research runtime: PyTorch 2.7.1+cu128 with two RTX 5090; isolated target deps.
- Module-local AGENTS.md files remain unnecessary at current size.
