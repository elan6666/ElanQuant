# Research — 2026-08-13

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
- Small is the current online release; the owner subsequently authorized an
  exact Base three-cell comparison on the same admitted data. Each fine-tune
  track fits its tokenizer and predictor on training data. Architecture/loss/optimizer/scheduler stay
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

## GitHub product benchmark — 2026-08-13

Current official repositories were rechecked by GitHub API and primary docs.
Stars are only a community signal, not proof of correctness.

- [Microsoft Qlib](https://github.com/microsoft/qlib) (47.3k stars, MIT,
  pushed 2026-07-23) makes experiment/run recorders, common-support evaluation,
  backtest and portfolio reports first-class. Adapt: immutable experiment
  lineage, split-aware metrics, support counts and run comparison. Avoid:
  replacing ElanQuant's admitted data or strict receipts with Qlib defaults.
- [VeighNa / vn.py](https://github.com/vnpy/vnpy) (44.4k stars, MIT,
  pushed 2026-08-10) exposes orders, fills, positions, risk and event-driven
  application boundaries. Adapt: explicit intent/fill/reject lifecycle and
  A-share board-lot explanation. Avoid: broker gateways and automatic trading.
- [MLflow](https://github.com/mlflow/mlflow) (27.5k stars, Apache-2.0,
  pushed 2026-08-12) emphasizes parameters, metrics, artifacts, registry and
  cross-run comparison. Adapt a small SQLite-backed lineage view; do not deploy
  a second tracking server for this single-user product.
- [Evidently](https://github.com/evidentlyai/evidently) (7.8k stars,
  Apache-2.0, pushed 2026-08-05) treats data tests and immutable monitoring
  snapshots as user-visible evidence. Adapt snapshot PASS/WARN/FAIL details,
  coverage, exclusions, finalization and caveats without adding its runtime.
- [QuantStats](https://github.com/ranaroussi/quantstats) (7.5k stars,
  Apache-2.0, pushed 2026-07-20) separates return-series metrics, plots and
  tear sheets and explicitly warns that period metrics are not trade metrics.
  Adapt sample-aware portfolio summaries that remain null when evidence is too
  short.
- [vectorbt](https://github.com/polakowo/vectorbt) (8.7k stars, active
  2026-08) provides portfolio/drawdown/trade analysis and fast scenario work.
  Adapt the analysis vocabulary only; its Commons Clause means code embedding
  deserves separate commercial-license review, and unconstrained parameter
  search would invite overfitting.
- [RQAlpha](https://github.com/ricequant/rqalpha) (6.7k stars, active
  2026-08) models A-share accounts, orders, risk and analysis as explicit
  modules. Adapt event names and execution receipts only; its non-standard
  commercial terms and separate paid data rule out direct embedding.
- [OpenBB](https://github.com/OpenBB-finance/OpenBB) (71.8k stars, active
  2026-07) demonstrates provider-neutral response metadata and composable
  research panels. Adapt source/as-of/availability/hash cards; avoid its AGPL
  code and multi-provider platform scope.
- [QuantConnect LEAN](https://github.com/QuantConnect/Lean) (21.2k stars,
  Apache-2.0, pushed 2026-08-12) cleanly separates fees, slippage, fills and
  order events. Adapt versioned execution assumptions, not its C# engine or
  live-broker surface.

## Product opportunities selected

1. Small/Base six-cell experiment center with 2025 validation and 2026
   `TEST_VIEWED` separated, including rows, cross-sections and zero-shot delta.
2. Run history/diff with Top-3 and Top-10 overlap and identity changes.
3. Data-health evidence: market finalization, 300/300 coverage, exclusion
   counts, membership availability and disclosed provider limitations.
4. Searchable/keyboard-accessible ranking with previous rank, three-track
   spread and paper-decision explanation.
5. Sample-aware simulated-account tear sheet and explicit board-lot/no-order
   decisions. Same-session force reruns must never mutate the first frozen
   paper publication.

No first-hand user complaints or analytics were available in this research
wave. The opportunities above are inferences from primary product behavior and
the owner's stated learning/audit needs, not simulated user feedback.
