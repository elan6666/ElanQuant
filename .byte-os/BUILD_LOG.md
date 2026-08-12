# Build Log

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
