---
id: 001
title: Repository and contracts foundation
status: complete
wave: 1
updated_at: 2026-08-12T15:43:00Z
owner_role: Tech Lead
depends_on: []
start_directory: .
context_files: [AGENTS.md, CLAUDE.md, .byte-os/TECH_SPEC.md]
agents_context_stack: [AGENTS.md]
subagent_policy: implementation_allowed
---

# Goal

Create installable Python/frontend packages, shared contracts, configuration,
and deterministic local verification.

# OKR Link

KR4.

# Scope

Python package, Vite app, configs, schema/migrations, provenance and fixtures.

# Non-Goals

No market download, training, or real broker.

# Steps

## Step 1: Scaffold packages
- Purpose: make commands real.
- Actions: add package metadata, entrypoints, frontend dependencies.
- Files or modules: `pyproject.toml`, `backend/`, `frontend/`.
- Expected output: importable backend and buildable frontend.
- Step verification: install, import, frontend build.
- Subagent: implementation_allowed

## Step 2: Add contracts and persistence
- Purpose: stable job/research/paper identities.
- Actions: add Pydantic types, SQLite schema/WAL, hashes/configs.
- Files or modules: `backend/src/elanquant/{contracts,storage,provenance}`, `configs/`.
- Expected output: deterministic schema and manifests.
- Step verification: focused pytest.
- Subagent: implementation_allowed

# Dependencies

None.

# Scoped Commands
- Test: `python -m pytest -q`
- Lint: `ruff check backend scripts tests`
- Typecheck: `pyright backend scripts`
- Build: `npm --prefix frontend run build`

# AGENTS.md Context
- Root context: `AGENTS.md`
- Module context: none
- Scoped command source: root harness
- Safe edit boundaries: new repo source only
- Missing or stale AGENTS.md notes: none

# Subagent Plan
- Implementation subagents: backend and frontend only with disjoint directories.
- Isolation boundaries: shared root files owned by main agent.
- Merge or handoff notes: main agent installs and verifies.

# Code Change Guardrails

Minimal dependencies; no distributed queue.

# Acceptance Criteria

Commands install/run, DB initializes, contract/hash tests pass.

# Verification

Backend tests/lint/typecheck and frontend test/build.

# Experiment Or Measurement

Cold startup and 202-API latency below one second without research work.

# Risks

Dependency/runtime mismatch on server.
