# UX Specification

## Core journey

`Connect VPN/SSH tunnel → open dashboard → inspect data/model status → press
Update data and run inference → follow durable stages → inspect data/experiment
evidence and ranking explanation → inspect frozen paper orders/account/history`.
The independent historical journey is `open Historical Backtest → confirm Top3
is retained → inspect sealed Top50 curve/metrics/parameters/deviations`; it has
no action button.

## Pages

- Overview: latest closed/data/inference dates, data health, primary model,
  warnings and action.
- Jobs: stage timeline, events, retries, duplicate/coalesced identity.
- Research: Small/Base six cells, 2025 validation vs 2026 `TEST_VIEWED`, sample
  support, zero-shot delta, run lineage and diff.
- Historical Backtest: official-demo-method identity, visible separation from
  Top3, fixed mean curve, four descriptive standardized signals,
  Top50/Drop5/Hold5 parameters, support, hashes and deviations. Missing evidence
  is a waiting state; tampered evidence is unavailable rather than approximated.
- Ranking: searchable/keyboard scores, ten-day signal, input completeness,
  previous rank, three-track spread, eligibility and paper decision.
- Stock detail: signal/model comparison and run evidence; do not draw a
  forecast band until an auditable per-session distribution exists.
- Paper account: cash, positions, intents, fills/rejections, NAV/gaps,
  sample-aware metrics and explicit Top-3 no-order reasons.
- Methods: plain-language full-stack, model, PIT, signal, execution and dual-track explanation.

## States

- Empty: explain first run and show no fabricated result.
- Loading: polling indicator without blocking navigation.
- Running: current stage and durable job ID; safe-to-close message.
- Data incomplete: exact field/session/coverage failure; no recommendation.
- Failed/interrupted: immutable failure and explicit retry.
- Success: as-of, model/data hashes, viewed/online status, next action.
- Stale: last result remains historical and is never relabeled current.

## Navigation

Persistent left/top navigation with research-risk notice. Primary action exists
only on Overview. Training controls are absent.

## First run

Explain VPN requirement, SSH tunnel command, manual update semantics, no real
account, and why latest online predictions are not yet scored.
