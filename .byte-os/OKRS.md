# Objective and Key Results

## Objective

Deliver ElanQuant as a trustworthy learning project and auditable daily A-share
research workflow, from official Kronos reproduction through strict-PIT paper
trading and a usable full-stack interface.

## Key Results

1. Freeze six cells across Small and Base: zero-shot, official-style
   extended-data fine-tune, and strict-PIT fine-tune, each with
   code/data/config/weight hashes and common-support split receipts.
2. Materialize and audit the agreed extended daily OHLCVA dataset from
   2011-01-01 through the latest closed session, with 2025 validation and 2026
   viewed evaluation separated by label-aware boundaries.
3. Complete the first workflow from `Update data and run inference` through a
   durable background job, ranked stocks, run/data evidence, and a dated paper
   order proposal that cannot be mutated by same-session force reruns.
4. Pass local backend/frontend tests and builds plus server data, training, and
   inference smoke/full gates without storing restricted artifacts in Git.
5. Complete three evidence-led iterations and a current ship review with clear
   limitations and operating instructions.
6. Correct the evaluation hierarchy: retain 2025 as training validation and
   checkpoint-selection evidence; preserve the initially leaked 2026 artifact
   as a diagnostic, publish a corrected opened out-of-sample diagnostic, and
   reserve a future untouched window for the next true final test.
7. Render every sealed historical curve point, including negative values and
   the zero baseline, without SVG clipping on desktop or mobile.

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
