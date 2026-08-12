---
schema_version: 1
mode: auto
project_kind: greenfield
stage: building
current_workflow: byte-build
next_workflow: byte-review
review_verdict: not_ship_external_gates
iteration_count: 2
harness_status: ready
hard_blocked: false
updated_at: 2026-08-13T01:40:00+08:00
---

# Current State

Foundation, durable backend, Chinese dashboard, strict contracts and deployment
bootstrap are implemented. Extended CSI300 v2 is PASS through 2026-08-12. The
owner narrowed this cycle to Small only: the formal official-style Small
Tokenizer is PASS and the Small Predictor is training on both server GPUs. The
Claude-inspired warm editorial dashboard is built, synced and browser-verified.

## Goal

Deliver an auditable A-share Kronos Small and strict-PIT research and
simulated-trading web system with server training and on-demand inference,
without real brokerage connectivity.

## Open blockers

- None. Server port 22 and the authenticated control session are healthy.

## Harness

Server verification currently passes 40 pytest tests, Ruff, Pyright, and compileall.
Frontend verification passes 7 Vitest tests, ESLint, TypeScript, and Vite build.
GitHub `main` is published and a fresh-clone backend/frontend verification passes.

## Next

Monitor `kronos-a-share-v2-20260813`, seal the Small three-cell receipt, run formal
evaluation, publish the release, start the Worker, then complete live E2E and
the third evidence-led iteration/final review.
