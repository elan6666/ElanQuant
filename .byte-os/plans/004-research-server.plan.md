---
id: 004
title: Strict PIT data, Kronos training, evaluation and inference
status: in_progress
wave: 2
updated_at: 2026-08-12T17:09:00Z
owner_role: Research Engineer
depends_on: ['001']
start_directory: scripts
context_files: [../AGENTS.md, ../.byte-os/RESEARCH.md, ../.byte-os/TECH_SPEC.md]
agents_context_stack: [AGENTS.md]
subagent_policy: none
---

# Goal

Produce terminal server receipts for extended data and three Small cells,
then expose a safe inference CLI to the worker.

# OKR Link

KR1, KR2, KR4.

# Scope

`scripts/`, research contracts/configs/tests, isolated remote worktree and artifacts.

# Non-Goals

No Mac workloads, real account, upstream model edits, or unlabelled deviations.

# Steps

## Step 1: Pin upstream and build audited extended data
- Purpose: causal inputs and reproducibility.
- Actions: verify commit/HF hashes; fetch approved data; materialize manifests,
  dynamic membership, OHLCVA, adjustment/tradability and strict splits.
- Files or modules: scripts/configs/tests; remote ignored artifacts.
- Expected output: PASS or typed data gate receipt.
- Step verification: future perturbation, continuity, split/hash tests.
- Subagent: none

## Step 2: Run official and strict Small matrix
- Purpose: Small evidence while Base is deferred by owner decision.
- Actions: zero-shot; official-style tokenizer/Small predictor; strict training-only
  tokenizer and Small predictor; immutable checkpoints/receipts.
- Files or modules: remote upstream pin, configs, runs/checkpoints.
- Expected output: three terminal Small model cells.
- Step verification: config/source/data/checkpoint reconciliation and metrics.
- Subagent: none

## Step 3: Add online inference and scoring
- Purpose: daily button pipeline.
- Actions: latest complete snapshot, N=10 paper signal, ranking, strict metadata.
- Files or modules: scripts/backend pipeline adapter.
- Expected output: immutable run artifact readable by API.
- Step verification: smoke and common-support repeatability.
- Subagent: none

# Dependencies

001 and free server resources.

# Scoped Commands
- Test: `.venv/bin/python -m pytest -q`
- Lint: `.venv/bin/ruff check backend scripts tests`
- Typecheck: `.venv/bin/python -m compileall -q backend scripts tests`
- Build: source manifest/hash verification

# AGENTS.md Context
- Root context: `AGENTS.md`
- Module context: none
- Scoped command source: root harness
- Safe edit boundaries: new scripts/configs; remote isolated artifacts
- Missing or stale AGENTS.md notes: none

# Subagent Plan
- Main agent only because server credentials/data/GPU jobs are sensitive.
- Review subagents may inspect copied-back small receipts read-only.

# Code Change Guardrails

Fail closed, exact pins, no result-driven tuning, no source mutation after receipt.

# Acceptance Criteria

Data passes; all cells terminal; strict online run and paper signal reproduce.

# Verification

Server tests/lint/compile, hashes, GPU/resource, inference repeatability.

# Experiment Or Measurement

Common-support IC/RankIC plus cost-aware paper metrics; selection only on 2025.

# Risks

Data coverage, runtime, official dependency compatibility.
