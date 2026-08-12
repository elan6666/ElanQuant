# Iteration 002 — Product and release hardening

Evidence from architecture and PIT re-review found a real `DATA_INCOMPLETE`
decoder failure, release/provenance races, weak publisher admission, inconsistent
missing-outcome semantics, execution fail-open on unobserved bars, and incomplete
paper valuation disclosure.

Changes: exact Small three-cell and finite-metric release validation, durable
worker heartbeat, consistent close-carry realized outcomes, observed-bar
execution gate, closed-world raw manifest, account valuation reconciliation,
Small-only frontend contracts, and a warm Claude-inspired responsive visual layer.

Verification: server 36 pytest, Ruff, Pyright and compile gates pass; frontend
7 tests, ESLint and production build pass; desktop and 390px browser QA pass.

Result: no open code-level P1 in the second architecture review. Real training,
release, disconnect E2E and Git delivery remain before SHIP.
