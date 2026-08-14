# UX Specification — ElanQuant v1

## Navigation

Six pages: Overview, Jobs, Experiment Matrix, Historical Backtest, Stock Ranking
and Paper Account. Methods is removed; its durable explanations move to README.

## Overview

- Heading: `更新数据，生成今天的研究结果`.
- Compact execution-profile selector above the single action.
- Local/remote labels describe running location, never a different model.
- Main surface shows dates, status and action only; hashes live in `查看审计信息` details.
- No VPN, SSH, Worker, SQLite, linger or AI-style slogan in the product path.

## Jobs

- Plain task progress, result number and local/remote badge.
- No architecture explanation. A submitted task says the page may be left and checked later.

## Experiment matrix

- Four visible cards: Small/Base x official zero-shot/official fine-tune.
- Strict-PIT never appears as a selectable card.
- RankIC, Pearson IC, Top10 realized return, sample rows and cross-sections have
  visible definitions and units. Viewed test is descriptive, never called best.

## Historical backtest

- Four public model selectors and Top50/Top3 portfolio selector.
- Only released evidence is selectable; no fallback to a retired strict cell.
- Cumulative return, benchmark, excess, drawdown, cost and turnover state their
  exact arithmetic/denominator semantics.
- Sealed daily holdings remain available with amount, value and portfolio weight.

## Ranking

- Rename signal to `10日预测涨跌`.
- Explain `mean(predicted closes for next 10 sessions) / current close - 1`.
- Example wording: 2.04% means predicted ten-day average close is 2.04% above
  current close; it is neither realized return nor probability.
- Show current reference price and derived predicted average when available.
- Input completeness and model-score spread include denominator/definition;
  raw per-model scores remain collapsed by default.

## First-run/reproduction

- One small README link below the main action.
- Missing profile is disabled and labelled not configured.
- Synthetic demo, zero-shot and full reproduction live in README/CLI, not new pages.

## Accessibility/responsiveness

- Definitions are visible text or keyboard-operable details, never hover/title only.
- 1440: compact Hero, four-card matrix, no unnecessary operational cards.
- 390: six bottom-nav items >=44px, two profile buttons >=44px, four model cards 2x2,
  tables scroll internally and page width never overflows.
- Focus is visible and browser console has no errors.
