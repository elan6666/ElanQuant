---
id: 011
title: Official-split data and four-cell release
status: complete
wave: 1
updated_at: 2026-08-14T07:50:00Z
owner_role: Research Tech Lead
depends_on: []
start_directory: scripts/server
context_files: [AGENTS.md, CLAUDE.md, .byte-os/TECH_SPEC.md]
agents_context_stack: [AGENTS.md]
subagent_policy: implementation_allowed
---

# Goal

Create new immutable v3 data, Small/Base training, mature rolling evaluation and
Top50/Top3 historical contracts without modifying old v2 artifacts.

# OKR Link

KR1, KR2, KR6.

# Scope

`scripts/server/`, `scripts/research/`, research configs/contracts and focused tests.

# Non-Goals

No old artifact deletion, no broker/SQLite mutation, no local training, no
fine-tuned-weight publication.

# Steps

## Step 1: Version official split contract

- Purpose: make raw and effective boundaries auditable.
- Actions: add v3 date constants, 101-row containment, mature-anchor and
  requested/actual backtest range receipts; add future-availability golden tests.
- Files or modules: dataset builder, split contracts, focused tests.
- Expected output: canonical PASS/FAIL split receipt.
- Step verification: focused pytest, Ruff, Pyright, compile.
- Subagent: implementation_allowed.

## Step 2: Version four-cell training matrix

- Purpose: train Small/Base official tokenizer+predictor only.
- Actions: create unique run IDs, official configs, terminal receipt compiler and
  retirement receipt; preserve author training behavior and pinned inputs.
- Expected output: exact four active cells with immutable hashes.
- Step verification: contract negative tests and shell syntax.
- Subagent: implementation_allowed.

## Step 3: Version evaluation and historical matrix

- Purpose: separate model evaluation from strategy backtest.
- Actions: mature TEST_VIEWED metrics; same-signal sample_count-5 Top50/Top3;
  four-model catalog; requested/actual dates and holdings.
- Expected output: fail-closed release/catalog schemas.
- Step verification: golden signal, support, common-hash and tamper tests.
- Subagent: implementation_allowed.

## Step 4: Execute server release

- Purpose: materialize real evidence.
- Actions: preflight, sync reviewed source, build/fetch frozen data, train
  Small/Base under persistent user-systemd, evaluate/backtest, independently audit.
- Expected output: admitted v3 candidate; old current untouched until final gate.
- Step verification: server receipts, GPU/process status, full gates.
- Subagent: none.

# Scoped Commands

- Test: `../app-venv/bin/python -m pytest -q tests/test_official_split_v3.py`
- Lint: `../app-venv/bin/ruff check scripts tests`
- Typecheck: `../app-venv/bin/pyright --pythonpath ../app-venv/bin/python scripts/research`
- Build: `../app-venv/bin/python -m compileall -q scripts tests`

# Acceptance Criteria

Official dates and 101-row semantics are exact; effective ranges do not cross;
four cells only; mature metrics only; Top50/Top3 signal hashes match; old release
hashes unchanged; every real terminal/evaluation/backtest receipt independently passes.

# Risks

Long GPU runtime; opened test cannot select parameters; provider revision limits remain disclosed.
