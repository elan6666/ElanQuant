# Iteration 003 — Evidence-chain product and Base comparison

The third iteration adopted the strongest reusable patterns from Qlib, MLflow,
Evidently, vn.py, QuantStats, vectorbt, LEAN and OpenBB without embedding their
code or adding a second platform. The product now follows one navigable chain:

`validated snapshot → sealed experiment → stock evidence → frozen paper ledger`

Changes include a Small/Base six-cell research catalog, separate 2025 validation
and 2026 `TEST_VIEWED` support, run history/diff, data health, stock-level track
spread and rank explanation, sample-aware paper metrics, explicit board-lot
outcomes and a same-session first-publication invariant. Forced research reruns
cannot mutate the first frozen paper publication. The React dashboard retains
the accepted Claude-inspired warm editorial system and adds keyboard search,
adaptive polling, responsive evidence tables and fail-closed decoders.

The live SQLite database was backed up with mode 0600, migrated while API and
Worker were stopped, and verified with `integrity_check=ok` and zero foreign-key
violations. Historical mixed-source orders were preserved and surfaced as
`LEGACY_MIXED_RUNS`; no rows were silently rewritten. Server verification passes
65 pytest tests, Ruff, Pyright and compileall. Frontend verification passes 10
Vitest tests, ESLint, production build and npm audit with zero vulnerabilities.

Base training was not repeated after an evaluation follower path error. Four
immutable Base stages and the existing three-cell matrix passed an independent
78/78 receipt/hash audit, including all 3,117 raw and seven processed files. A
separate recovery entrypoint consumes that sealed matrix, writes only previously
absent smoke/formal/catalog outputs, and cannot promote `releases/current`.

Final result remains pending until the Base FORMAL receipt, same-session live
evidence refresh and deployed desktop/mobile design QA complete.
