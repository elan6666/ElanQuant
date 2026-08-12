# Codebase Map

## Repository state

Greenfield repository with the v0 implementation in place.

## Top-level map

| Path | Purpose | Normal source? |
|---|---|---|
| `backend/` | FastAPI control plane and paper account | yes |
| `frontend/` | React/TypeScript dashboard | yes |
| `scripts/` | Server-only research and operational entrypoints | yes |
| `tests/` | Python integration and contract tests | yes |
| `docs/` | Operator, provenance, and learning guides | yes |
| `.byte-os/` | Lifecycle, specs, plans, review, delivery | yes |
| `data/`, `runs/`, `weights/`, `checkpoints/` | Restricted generated research artifacts | no |

## Stacks and package managers

- Python 3.11+: FastAPI, Pydantic, SQLite, pandas/numpy, pytest, Ruff, Pyright.
- Node 20+: React, TypeScript, Vite, Vitest, ESLint.
- Research runtime: official pinned Kronos/PyTorch on the server only.

## Scoped command matrix

| Scope | Test | Lint | Type/build |
|---|---|---|---|
| Backend/scripts | `python -m pytest -q` | `ruff check backend/src scripts tests` | `pyright backend/src scripts/research` |
| Frontend | `npm --prefix frontend test` | `npm --prefix frontend run lint` | `npm --prefix frontend run build` |
| Server | `app-venv/bin/python -m pytest -q` | `app-venv/bin/ruff check backend/src scripts tests` | `app-venv/bin/pyright backend/src scripts/research` |

## Generated/noisy paths

`.git/`, `.venv/`, `node_modules/`, `dist/`, coverage, caches, `data/`,
`artifacts/`, `runs/`, `reports/generated/`, `logs/`, `checkpoints/`, `weights/`.

## LSP recommendations

- Python: Pyright/Pylance or basedpyright.
- TypeScript/React: tsserver through the editor.
- Fallback: `rg`, direct reads, package metadata, and focused tests.

## Exploration candidates

- Official Kronos fidelity: upstream repository, paper, weights, train configs.
- PIT/data: membership, availability, adjustment, split/embargo, scoreable dates.
- App/runtime: background job durability, SSH-tunnel access, result schema.
