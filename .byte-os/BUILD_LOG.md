# Build Log

## 2026-08-13 — Historical Top3 sensitivity and holdings

- Added a fully isolated Qlib Top3/Drop1/Hold5 post-hoc portfolio sensitivity
  track beside the official Top50 baseline for 2025 validation and opened 2026.
- Sealed an exact four-cell catalog and daily per-instrument holdings for every
  cell. Top50 replay matches old receipts below 4e-15 maximum absolute error.
- Added bounded hash-checked holdings GET and a responsive session viewer.
- Mean Top3 returned -28.52% in 2025 and -17.47% in opened 2026; neither result
  is selectable or promotable.
- Final gates: 97 server tests, Ruff, Pyright and compileall PASS; 17 frontend
  tests, ESLint, build and browser QA PASS. Paper/current release unchanged.

## 2026-08-12 — Foundation and implementation waves

- Initialized independent `elan6666/ElanQuant` checkout and Byte OS artifacts.
- Pinned Kronos upstream commit and three official Hugging Face revisions/hashes.
- Implemented strict split, future-as-of hash, inverse close signal, deterministic
  DDP sampling, T-frozen board-lot intent, T+1 rejection, and experiment matrix contracts.
- Implemented FastAPI, SQLite WAL durable queue, separate Worker, result APIs,
  real/placeholder pipeline boundary, simulated account and systemd templates.
- Implemented React/TypeScript Chinese dashboard and runtime API decoders.
- Implemented resumable full historical fetch, processed dataset builder,
  isolated workspaces, smoke/full training matrix, evaluation, immutable online
  snapshot and real inference publication.
- Added README, research protocol, operations guide and learning guide.

### Verification recorded

- Frontend: 6/6 Vitest PASS; ESLint PASS; TypeScript/Vite production build PASS.
- Server backend/research contracts: 20/20 pytest PASS; Ruff PASS; Pyright
  0 errors; compileall PASS; training shell syntax PASS.
- Official weights receipt: PASS for Tokenizer-base, Small and Base SHA-256.
- Preflight: two RTX 5090 32GB GPUs idle; about 1.7TB free.

### In progress

- `elanquant-fetch-extended-csi300-v1-r2` is the sole active data-fetch unit.
- Dataset materialization, GPU smoke, full training, evaluation, live services,
  browser/disconnect E2E, reviews and three iterations remain.

### Known caveats

- The approved tutorial data proxy uses plain HTTP; no credential bytes are
  copied or logged, but transport confidentiality is limited.
- Server user manager initially reported `Linger=no`; it is now enabled and must
  still pass the live submit/disconnect/reconnect E2E before delivery.
- One Starlette TestClient deprecation warning is upstream dependency noise;
  test behavior passes.

## 2026-08-13 — Admission repair and formal training

- Three independent reviews initially returned NOT SHIP and identified future
  missingness selection, unproved market-close state, mutable provenance,
  non-atomic publication, unsealed matrix identities and an unverified VPN
  durability claim.
- Rebuilt `extended-v2` through 2026-08-12: 775 historical symbols, 300 latest
  eligible symbols, and 989,784/69,600/40,800 strict train/validation/viewed-test
  anchors. Future missingness no longer changes T-day eligibility; membership is
  conservatively lagged one complete session with vendor revision limits disclosed.
- Verified a 64 MiB two-rank collective plus Kronos DDP backward over loopback
  socket transport; the earlier six-stage smoke passed. The owner subsequently
  narrowed formal delivery to Small only, so the admitted matrix now has three cells.
- Added immutable stage/run receipts, fresh-checkpoint gates, matrix derivation,
  runtime upstream/checkpoint verification, formal evaluation support hashes,
  immutable per-run model provenance, unscored online forecasts, atomic job/run/
  paper publication, structured data gates, worker heartbeat, Host/Origin/CSP
  guards, T+1 available quantities, suspension/ST rejection and manual-run gaps.
- Server: 30 pytest PASS, Ruff PASS, Pyright 0 errors and compileall PASS.
  Frontend: 6 Vitest PASS, ESLint PASS, TypeScript/Vite build PASS. Desktop and
  390px browser QA have no horizontal overflow or console errors. API is
  loopback-only and truthfully degraded until
  training/evaluation receipts and Worker are available.
- The immutable 2026-08-12 online snapshot is PASS for 300/300 members and all
  three payload hashes. `Linger=yes` is enabled for the server user.
- Formal Small run `kronos-a-share-v2-20260813` is active with 30 epochs, 2 GPUs,
  batch 50/GPU, 100k train and 20k validation samples per epoch. Base training
  was stopped before it began. A server-side follower will compile, smoke,
  formally evaluate and atomically publish the Small release after training.

## 2026-08-13 — Iteration 2 product and release hardening

- Replaced the initial dashboard skin with an original Claude-inspired warm
  editorial system: cream surfaces, terracotta action color, dark-brown type,
  serif display headings, calm navigation and restrained depth. Desktop and
  390px screenshots show no horizontal overflow; browser console errors are zero.
- Removed the final Base/infer-base runtime residues, added actual Pearson IC and
  Top10 return contracts, and made `DATA_INCOMPLETE` decode into the validation
  stage instead of crashing the dashboard refresh.
- Added exact three-Small-cell gates at inference and release publication,
  matrix/evaluation/data race rechecks, finite formal metric and coverage gates,
  long-subprocess heartbeats and auditable paper-account valuation fallback.
- Closed PIT issues in realized-outcome consistency, observed-session execution
  eligibility and raw-data closed-world manifest verification. Online snapshots
  now bind reuse to the snapshot implementation hash.
- Latest gates: server 36 pytest PASS, Ruff PASS, Pyright 0, compileall and shell
  syntax PASS; frontend 7 Vitest PASS, ESLint PASS and production build PASS.

## 2026-08-13 — Delivery reproducibility and data admission

- Sealed `runs/admission/extended-v2.json`: 3,117 raw CSV files and seven
  processed files passed closed-world path, endpoint, symbol, row-count,
  date-range and SHA-256 verification. The Small matrix compiler now requires
  this receipt and binds its hash.
- Persisted per-position valuation price/source/value/PnL in each portfolio
  snapshot. API account totals now reconcile exactly to the displayed position
  ledger; legacy and T+1 migration paths have direct tests.
- Server verification now passes 40 pytest tests, Ruff, Pyright, compileall and
  shell syntax. `npm audit --omit=dev` reports zero vulnerabilities.
- Published GitHub `main` to `elan6666/ElanQuant` with an MIT license and no
  data, credentials, weights, checkpoints, predictions, databases or logs.
- A fresh GitHub clone passed `npm ci`, seven frontend tests, ESLint and build on
  Mac; a separate fresh server virtualenv passed 40 tests, Ruff, Pyright and
  compileall.

## 2026-08-13 — Base supplement and evidence-chain iteration 3

- Parameterized the author-aligned training/matrix/evaluation entrypoints for an
  isolated Base three-cell candidate while preserving Small defaults and
  prohibiting Base promotion to `releases/current`.
- Started durable two-GPU Base training under systemd and a separate finalizer;
  the remote work survives Mac/VPN disconnect. Final receipt audit remains
  pending because the old SSH ControlMaster expired while port 22 stayed reachable.
- Researched current primary-source patterns from Qlib, MLflow, Evidently,
  vn.py, QuantStats, vectorbt, LEAN and OpenBB. Adapted run lineage, split-aware
  support, data-health receipts, explicit order outcomes and evidence-aware
  portfolio summaries without embedding third-party code or adding runtimes.
- Added exact same-session paper publication freezing, zero-order legacy
  migration, commission-reserving board-lot sizing, deterministic rank order,
  immutable per-run evaluation identities and final snapshot-file revalidation.
- Added six-cell catalog producer/consumer gates, run history/diff, data health,
  stock explanations, paper summary, adaptive polling and optional catalog
  degradation so a bad research catalog cannot take down the control plane.
- Extended the Claude-warm editorial UI; the accent was darkened to `#a84d30`
  for AA contrast (5.37:1 with warm white text, 5.07:1 on the paper background).
- Current local gates: 42 focused Python tests, Ruff, compileall and diff-check
  PASS; 10 frontend tests, ESLint, build and npm audit PASS. Independent static
  review is SHIP; full server/API, live migration/data refresh and deployed
  1440/390 QA remain delivery gates.

## 2026-08-13 — Isolated official-demo method version

- Preserved the existing manual Top3 strict-PIT online/paper product and added a
  separate artifact/catalog-only historical research version. It has no POST,
  job, recommendation, order, position, fill or NAV write path.
- Reproduced the pinned Kronos demo method with 90-session instance
  normalization, sample count five, standardized-space last/mean/max/min close
  differences, and Qlib Top50/Drop5/minimum-hold-five delayed next-open
  execution. pyqlib 0.9.7 and all provider/code/config/model identities are
  recorded because the author repository does not pin Qlib.
- Sealed 67,349 signal rows over 233 validation-2025 cross-sections and a
  233-session backtest. The predeclared mean signal returned 7.03% after cost
  versus 16.30% for SH000300, with -9.27% excess and -11.78% maximum drawdown;
  the product therefore labels this as a method baseline, not alpha evidence.
- Published fail-closed GET-only API endpoints and a dedicated Chinese
  `历史回测` page with a direct Top3-versus-official comparison, four signals,
  execution constants, hashes and Chinese deviation disclosure.
- Recomputed the sealed release and catalog hashes successfully. A before/after
  audit found every Top3 paper table unchanged. A later same-session Top3 force
  refresh succeeded on the second GPU, published 900 scores and six split
  evaluation rows, skipped the already-frozen paper publication, and left the
  frozen ledger byte-for-byte unchanged.
- Final server gate: 73 pytest PASS, Ruff PASS, Pyright 0 errors/warnings,
  compileall PASS, shell syntax PASS and systemd unit verification PASS. Frontend: 12 Vitest PASS, ESLint,
  production build and zero-vulnerability npm audit PASS. Live 1440 and 390 px
  browser QA has no overflow or console warnings/errors.

## 2026-08-13 — Base formal and six-cell delivery

- Base formal evaluation finished after two hours without retraining. Independent
  reconciliation passed 677/677 matrix/formal checks; the resulting six-cell
  catalog passed 110/110 checks and the live GET returns exactly three Small and
  three Base cells on identical 18,000-row/60-section validation and
  10,500-row/35-section viewed-test support.
- The first catalog attempt correctly stopped because Small used an older raw
  config/code identity. Rather than edit immutable evidence or rerun, added a
  fail-closed semantic compatibility receipt binding both original hashes,
  exact Git revisions, a normalized batch/sampling protocol and an exact
  reviewed source-diff SHA. Tampered diff, revision, identity and receipt paths
  are rejected by producer, API consumer and tests.
- Base validation RankIC is 0.03465 zero-shot, 0.02294 official FT and 0.01342
  strict PIT. Base strict has the largest Top10 mean but negative Pearson IC;
  no Base cell is promoted. `releases/current` and the live primary model remain
  Small r2 / `small-strict-pit`.
- Final server suite: 75 pytest PASS, Ruff PASS, Pyright 0 errors/warnings and
  compileall PASS. Independent Base/catalog audit and final product/design
  reviews are SHIP with no P0/P1.

## 2026-08-13 — Corrected opened 2026 diagnostic and chart repair

- Corrected the historical SVG layout with a bounded grid plot area and a
  separate footer, eliminating the clipped curve at desktop and mobile widths.
- Recorded that 2025 validation loss selected the best checkpoint after all 30
  epochs; the product no longer presents that period as independent test data.
- Rejected the first 2026 strategy artifact after review found that eligibility
  depended on future symbol rows. Preserved it for audit, removed it from the
  active catalog, and added golden tests for T-known eligibility.
- Produced the corrected r5 diagnostic with prior-90-global-session context and
  next-ten-global-exchange timestamps: 39,072 signal rows across 137 sessions.
  The predeclared mean signal returned -7.65% after cost versus +0.45% for
  SH000300, with -8.09% excess and -13.31% maximum drawdown.
- Published catalog v3 without changing the Small r2 release or any Top3 paper
  table. The active page labels 2026 as opened, non-selection diagnostic and
  reserves a future untouched window for the next true final test.
- Final gates: server 80 pytest PASS, Ruff PASS, Pyright 0 and compileall PASS;
  frontend 12 Vitest PASS, ESLint, production build and npm audit PASS. Live
  API/security checks and deployed visual QA pass; independent design review is
  SHIP with no P0/P1/P2.

## 2026-08-14 — Official split portability and build wave

- Fetched and admitted the official raw slices through the frozen 2026-08-13
  session, preserving raw-slice overlap only as lookback context and proving
  effective 101-row train/validation and mature rolling-test boundaries.
- Added exact Small/Base × zero-shot/official-FT contracts, retirement receipts
  for old Strict PIT evidence, persistent two-GPU training, four-cell signal
  evaluation and eight Top50/Top3 historical producers.
- Added explicit Apple Silicon and Linux/NVIDIA execution identities with no
  silent device fallback. Mac PyTorch 2.13 MPS and server PyTorch 2.13+cu130
  RTX 5090 CUDA doctor/synthetic smoke receipts are PASS.
- Added public BYO CSV/Parquet import, pinned official Tokenizer/Small/Base
  weight verification, bootstrap, package metadata, data/license documentation
  and three-level README reproduction instructions.
- Simplified the dashboard to six pages and four public model cells; removed
  Strict PIT selectors and operational prose, added visible numeric definitions
  and a reference-price explanation for the 10-day predicted percentage.
- Added v3 API/UI adapters for the exact four-model Rolling Test and all eight
  historical Top50/Top3 receipts, including sealed daily series and holdings.
- Current gates: frontend 22 tests, ESLint and build PASS; server 132 tests,
  Ruff, compileall and scoped Pyright PASS. Wheel/sdist build and a clean Python
  3.12 wheel install/data-import/bootstrap smoke PASS with no forbidden payloads.
