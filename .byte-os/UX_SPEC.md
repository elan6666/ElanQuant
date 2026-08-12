# UX Specification

## Core journey

`Connect VPN/SSH tunnel → open dashboard → inspect data/model status → press
Update data and run inference → follow durable stages → inspect ranking and
stock forecast → inspect frozen paper orders/account/history`.

## Pages

- Overview: latest closed/data/inference dates, primary model, warnings, action.
- Jobs: stage timeline, events, retries, duplicate/coalesced identity.
- Research: three Small cells, metrics, official/PIT labels, provenance.
- Ranking: scores, forecast return, coverage, eligibility, explanations.
- Stock detail: 90-day context, ten-day path distribution, model comparison.
- Paper account: cash, positions, intents, fills/rejections, NAV and gaps.
- Methods: plain-language full-stack, model, PIT, signal, execution explanation.

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
