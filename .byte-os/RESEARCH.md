# Research — 2026-08-12

## Scope

Primary-source review of Kronos, Qlib, strict-PIT A-share data/execution, and a
VPN-disconnected on-demand inference product.

## Official Kronos facts

- Pin upstream commit
  [`67b630e67f6a18c9e9be918d9b4337c960db1e9a`](https://github.com/shiyu-coder/Kronos/commit/67b630e67f6a18c9e9be918d9b4337c960db1e9a),
  MIT licensed.
- Official Small (24.7M) and Base (102.3M) both use
  `Kronos-Tokenizer-base`, context 512. Official weights are available, but no
  official A-share fine-tuned checkpoint is published.
- The official A-share demo uses CSI300 daily OHLCVA, 90 lookback, 10 forecast,
  30 epochs, batch 50/GPU, 100k sampled train and 20k validation windows per
  epoch, seed 100, OneCycleLR, tokenizer LR 2e-4, predictor LR 4e-5, and weight
  decay 0.1. It trains the tokenizer, freezes it, then trains the predictor.
- The official README explicitly describes the pipeline as a simplified demo,
  not a production-ready strategy. [Official repository](https://github.com/shiyu-coder/Kronos)
- The paper investment signal is the mean of ten predicted future closes
  relative to current close, with T=0.6, top-p=.9, and ten Monte Carlo paths.
  [Paper](https://arxiv.org/abs/2508.02739)

## Material official-demo limitations

- Official raw slices overlap train/validation and validation/test for context,
  but code does not separately constrain formal anchor/target dates; labels can
  overlap.
- Demo `amount` is an OHLC-average-times-volume proxy, not a loaded true amount.
- Missing rows are dropped without proving remaining rows are consecutive.
- Dataset ignores the requested index and samples randomly, weakening DDP
  disjointness/reproducibility.
- Repository backtest signals remain in normalized per-stock space and use five
  samples; they are not identical to the paper's inverse-transformed percentage
  return signal and ten paths.
- Current published tokenizer config differs from the paper table in layer and
  group-size details. Published weight/config is the executable baseline; the
  difference belongs in the deviation ledger.

## Strict PIT contract

- Raw range: 2011-01-01 through `LATEST_CLOSED_SESSION`.
- Each anchor uses exactly 90 completed sessions and targets the next 10.
- Train target end <= final 2024 session; validation anchors start in 2025 and
  targets end in 2025; viewed test anchors start in 2026 and targets end no later
  than latest closed session. Latest closed anchor is online-only until labels
  mature.
- Historical dynamic CSI300 membership is mandatory; current membership cannot
  be backfilled. The index methodology permits regular and temporary changes.
  [CSI300 methodology](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000300_Index_Methodology_cn.pdf)
- Inputs bind availability time, raw prices, adjustment factors, tradability,
  ST/suspension/limit state, source/version/hash, and causal adjustment view.
- This cycle admits Small only. Each fine-tune track fits its tokenizer and
  predictor on training data. Architecture/loss/optimizer/scheduler stay
  official; audited data, inverse transform, signal, and execution boundaries
  remain explicitly labeled ElanQuant adaptations.

## Execution and paper account

- T close freezes rank, target holdings, and order quantity using T-known data.
- T+1 open only fills or rejects. A rejected order leaves cash/holdings intact
  and cannot be replaced using T+1 information.
- MVP account: RMB100,000, long-only Top-3, 100-share board lots, next-open
  execution, no leverage. It does not yet implement minimum holding periods,
  slippage, stress reports, corporate actions, or full target rebalancing.
- Implemented paper costs are 0.03% commission, RMB5 minimum, and 0.05% sell
  stamp duty. [Tax authority](https://fgk.chinatax.gov.cn/zcfgk/c102416/c5211343/content.html)
- Qlib TopkDropoutStrategy is retained only for official-comparison reporting.
  [Qlib strategy docs](https://qlib.readthedocs.io/en/latest/component/strategy.html)

## Product/runtime findings

- Use one loopback FastAPI/static frontend service, SQLite WAL durable metadata,
  and an independent systemd user worker. A button returns HTTP 202 after an
  idempotent insert; polling observes progress. Browser/VPN disconnect cannot
  kill the job.
- Use an SSH local tunnel through EasyConnect. No public bind and no automatic
  VPN login.
- GPU lives only in a child inference/training process. Daily inference and
  model training are separate job families.
- Manual use means skipped decision days are explicit gaps; do not fabricate
  continuous historical decisions afterward.

## Product implications

1. Show official-reproduction and strict-PIT results separately.
2. Fail closed on data incompleteness or identity/hash mismatch.
3. Make provenance, scoreability, viewed-test status, rejection, and cash
   visible in the UI.
4. Keep real brokerage connectivity outside v0.
