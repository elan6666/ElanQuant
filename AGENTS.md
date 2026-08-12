# AGENTS.md

## Project Purpose

Build an auditable, research-only A-share Kronos Small/Base comparison with
strict PIT data, on-demand Small server inference, and a simulated trading
account. Base is an admitted research candidate only and must never replace the
Small live release without a separate evidence-backed owner decision.

## Start Here

- Current state: `.byte-os/STATUS.md`
- Product/technical scope: `.byte-os/PRODUCT_SPEC.md`, `.byte-os/TECH_SPEC.md`
- Codebase map: `.byte-os/CODEBASE_MAP.md`
- Harness: `.byte-os/HARNESS.md`
- Plans: `.byte-os/plans/`

## Repository Map

- `backend/`: FastAPI control plane, job state, result APIs, paper account.
- `frontend/`: React/TypeScript owner dashboard.
- `scripts/`: server-only data, training, inference, and operations entrypoints.
- `tests/`: cross-module contract and security tests.
- `docs/`: operator and learning documentation.
- `.byte-os/`: product state, plans, reviews, iterations, delivery evidence.

## Global Commands

- Backend tests: `python -m pytest -q`
- Backend lint: `ruff check backend scripts tests`
- Backend typecheck: `pyright backend/src scripts/research`
- Frontend tests: `npm --prefix frontend test`
- Frontend lint: `npm --prefix frontend run lint`
- Frontend typecheck/build: `npm --prefix frontend run build`

## Server Boundary

- All market-data downloads, dataset builds, training, inference, evaluation,
  paper ledgers, reports, checkpoints, and weights run only under
  `/data/yilangliu/a_share_research/elanquant` on `yilangliu@10.24.1.91`.
- Before server work, verify port 22, remote path, GPUs, and free space.
- Never write a password/token to commands, logs, source, or chat.
- Never commit data, weights, checkpoints, logs, generated reports, or secrets.

## Safe Edit Boundaries

- Prefer: `backend/`, `frontend/src/`, `scripts/`, `tests/`, `docs/`, `.byte-os/`.
- Avoid: pinned official upstream model internals and legacy sibling projects.
- Generated/noisy: `data/`, `artifacts/`, `runs/`, `reports/generated/`,
  `logs/`, `checkpoints/`, `weights/`, caches, dependencies, build outputs.

## Navigation

- Python: Pyright/Pylance; TypeScript: tsserver.
- Use `rg`/`rg --files` when symbol navigation is unavailable.
- Start in `backend/`, `frontend/`, or `scripts/` according to the active plan.

## Subagents

- Exploration is read-only and bounded by one subsystem or research question.
- Implementation requires disjoint plan-owned directories and verification.
- Reviews remain read-only for PIT, official fidelity, security, and UX.

## Maintenance

- Last reviewed: 2026-08-13
- Next review: after the Base candidate and six-cell catalog are sealed
- Owner/DRI: root integrator
