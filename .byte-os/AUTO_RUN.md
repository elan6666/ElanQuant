# Byte Auto Run

- Goal: deliver the official-split Small/Base retraining reset, rolling-test
  evaluation and Top50/Top3 backtests, local/remote inference, third-party
  reproducibility and simplified evidence-led product.
- Started at: 2026-08-14T15:43:00+08:00
- Current loop: 1
- Completed stages: prior v0 delivery; official-split discussion; new goal;
  harness; official-split data fetch/materialization/admission; portable
  execution profiles; Mac MPS and server CUDA doctor/synthetic smoke; BYO
  CSV/Parquet and pinned official-weight bootstrap; simplified four-cell UI;
  v3 evaluation/history/online adapters; Small Tokenizer/Predictor training.
- Remaining plans: finish Base Tokenizer/Predictor training; seal four-cell
  matrix, analysis lock, four signals and eight Top50/Top3 backtests; publish
  and independently audit the new release; deploy, run real online E2E,
  complete three review-led iterations and delivery.
- Review verdict: pending.
- Iteration count: 0/3 for the current change.
- Subagent mode: on; official training/data, portable runtime/reproduction and
  product UX exploration have disjoint read-only scopes. Implementation scopes
  will be assigned only after plan files freeze ownership.
- Hard blockers: none. Fine-tuned-weight publication is a conditional delivery
  item gated by license evidence, not a blocker for code/recipe delivery.
- Exact resume action: keep the persistent Base training and dependent
  matrix/lock/analysis/sealer services under observation; once receipts exist,
  independently rehash and audit them before publishing or switching current.
- Parked future items: 0, excluded from Auto.
