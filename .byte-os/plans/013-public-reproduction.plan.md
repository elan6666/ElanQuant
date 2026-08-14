---
id: 013
title: Public data, weights, bootstrap and package
status: in_progress
wave: 1
updated_at: 2026-08-14T07:50:00Z
owner_role: Developer Experience Engineer
depends_on: []
start_directory: .
context_files: [AGENTS.md, CLAUDE.md, .byte-os/PRODUCT_SPEC.md]
agents_context_stack: [AGENTS.md]
subagent_policy: implementation_allowed
---

# Goal

Let a third party reach synthetic demo, official zero-shot and full BYO-data
reproduction without private infrastructure or bundled restricted artifacts.

# OKR Link

KR4, KR9.

# Scope

CLI data/weights/bootstrap, configs, packaging, synthetic fixture, licenses and tests.

# Non-Goals

No bundled market data/token, no hosted service, no A-share checkpoint upload
without license approval.

# Steps

## Step 1: Canonical BYO data importer
- Actions: CSV/Parquet schema mapping, validation, canonical hash/receipt, optional
  token-file Tushare adapter and secret-safe failure modes.
- Verification: CSV=Parquet golden, malformed/timezone/OHLC/future/universe negatives.
- Subagent: implementation_allowed.

## Step 2: Official weight manager
- Actions: Small default/Base opt-in, pinned revisions, allowlist/tree hash,
  fetch/verify/offline/check-only, license inventory.
- Verification: cached/offline/corrupt/extra-file tests.
- Subagent: implementation_allowed.

## Step 3: Bootstrap and distributable package
- Actions: staged dry-run/resume receipts, synthetic fixture, wheel/sdist,
  third-party notices and data policy.
- Verification: package-content scan, no data/weights/secrets/private host.
- Subagent: implementation_allowed.

# Acceptance Criteria

Every public command is real and tested; README can reproduce all three tiers;
wheel/sdist contains only source/config/docs/synthetic fixture.
