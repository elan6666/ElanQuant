---
id: 006
title: Official-aligned Base three-cell experiment
status: in_progress
wave: 4
updated_at: 2026-08-13T05:10:00+08:00
owner_role: Research Engineer
depends_on: ['004']
start_directory: scripts
context_files: [../AGENTS.md, ../.byte-os/RESEARCH.md, ../docs/RESEARCH_PROTOCOL.md]
agents_context_stack: [AGENTS.md]
subagent_policy: plan_owned_implementation
---

# Goal

Run the exact Base zero-shot, official-style fine-tune and strict-PIT fine-tune
comparison on the already admitted extended-v2 dataset without changing the
live Small release.

# Scope

Model-size-generalized training/matrix/evaluation entrypoints; four immutable
Base training stages; common-support FORMAL evaluation; six-cell research
catalog consumed by the product.

# Non-Goals

No online Base promotion, no hyperparameter search, no data/split changes, no
publication of generated artifacts to Git.

# Steps

1. Generalize author-aligned entrypoints with Small-preserving defaults and
   focused tests.
2. Preflight remote path, space, two GPUs, data/admission/upstream/weight hashes;
   run four sequential 30-epoch DDP stages with immutable receipts.
3. Compile the exact Base matrix, run common-support 2025 validation and 2026
   TEST_VIEWED evaluation, then build a safe six-cell research catalog.
4. Independently reconcile every checkpoint/config/data/source/support hash and
   report metrics without result-driven model promotion.

# Acceptance Criteria

- Four Base terminals and exact three-cell matrix are PASS and reproducible.
- All three cells share the same frozen evaluation support for both splits.
- Small live release and paper model are unchanged throughout the experiment.
- Product catalog exposes all six cells without absolute paths or secrets.

# Verification

Focused research tests, Ruff, compileall, shell syntax, receipt/hash audit,
GPU-release check and read-only live API confirmation.
