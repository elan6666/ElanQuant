# Objective and Key Results

## Objective

Deliver ElanQuant as a reproducible, auditable Kronos A-share research product
that another technical user can run locally or on their own GPU server without
depending on the owner's private infrastructure.

## Key Results

10. Integrate the sealed iTransformer B2 CSI300 strict-weekly model as a
    first-class research family beside Kronos: model-aware matrix, historical
    comparison and artifact-only weekly ranking snapshots with explicit cadence.

1. Freeze four active cells across Small and Base: official zero-shot and new
   official-date-aligned fine-tune, with code/data/config/weight hashes and
   immutable training receipts; retire strict-PIT from public product selectors.
2. Materialize and audit raw train/validation/test slices aligned to the pinned
   Kronos demo dates through a frozen latest close, with 101-row training
   windows, mature T+10 evaluation anchors and explicit ROLLING_TEST_VIEWED state.
3. Complete the first workflow from `Update data and run inference` through a
   durable background job, ranked stocks, run/data evidence, and a dated paper
   order proposal that cannot be mutated by same-session force reruns.
4. Pass local backend/frontend tests and builds plus server data, training, and
   inference smoke/full gates without storing restricted artifacts in Git.
5. Complete three evidence-led iterations and a current ship review with clear
   limitations and operating instructions.
6. Publish model evaluation separately from strategy backtesting: IC/RankIC use
   only matured rolling-test labels, while Top50/Drop5/Hold5 and
   Top3/Drop1/Hold5 share the exact same sample-count-five standardized signals.
7. Render every sealed historical curve point, including negative values and
   the zero baseline, without SVG clipping on desktop or mobile.
8. Admit local Apple Silicon and configurable remote Linux/NVIDIA execution
   profiles with equivalent model-evidence identity, device-specific smoke
   receipts and Small default/Base opt-in resource gates.
9. Provide a zero-to-running public path: official weight download, BYO
   CSV/Parquet import, optional user-owned Tushare adapter, bootstrap/doctor,
   concise README and no private paths, credentials or generated artifacts.

## Baseline

- GitHub repository existed but was empty at Auto start.
- Official global Kronos weights exist; no official A-share fine-tuned weights
  were identified in the prior discussion.
- Server and VPN route are available, but no ElanQuant service or trained
  ElanQuant checkpoint exists yet.

## Evidence required

- Official upstream commit and weight identifiers.
- Dataset manifests, availability rules, split receipts, hashes, and coverage.
- Training/inference receipts and metrics for every admitted cell.
- Paper orders, fills, cash/position reconciliation, costs, and rejection logs.
- Test, lint, typecheck, build, browser, server, review, and iteration records.
