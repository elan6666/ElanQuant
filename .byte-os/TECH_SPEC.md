# Technical Specification — ElanQuant v1

## Architecture

- React/TypeScript/Vite frontend served by FastAPI.
- Loopback FastAPI + SQLite durable jobs + independent worker.
- Versioned research CLIs produce immutable data, training, evaluation and
  historical-backtest artifacts outside Git.
- A portable runtime layer resolves deployment profile, release and device
  before any job is claimed.

## Identity model

`ModelEvidenceIdentity` binds upstream commit, predictor/tokenizer/config,
matrix and evaluation hashes. `ExecutionIdentity` binds profile, OS/arch,
Python/Torch, device backend/name, batch schedule and inference code. `DataIdentity`
binds canonical data hash, schema mapping, calendar/universe declarations and
provenance. Local/remote changes only ExecutionIdentity.

## Official-split dataset v3

- Input: immutable closed-world raw manifest or canonical BYO-data receipt.
- Outputs: per-symbol train/val/test pickles plus manifest and effective-range receipt.
- Training windows are exactly 101 rows and fully contained in their raw slice.
- Test inference windows use 90 context + next 10 global exchange timestamps;
  candidate eligibility never reads future symbol availability.
- The manifest records requested/frozen end, actual coverage, raw ranges,
  effective first/last anchors and targets, exclusions and every file SHA.

## Model release v3

- Active cells: two sizes x zero-shot/official-ft.
- Small and Base each train official tokenizer then predictor from pinned weights.
- Author optimizer, scheduler, loss, sampling and 30-epoch behavior are preserved.
- Unique immutable run directories; old v2 current remains until v3 admission passes.
- Retirement receipt points to superseded v2 evidence; it never deletes it.

## Evaluation/backtest

- Mature evaluation end is derived from the frozen calendar, never guessed by dates.
- Rolling evaluation schema labels `TEST_VIEWED`, `used_for_selection=false`.
- Historical matrix: four model cells x Top50/Top3 over one viewed rolling backtest
  window, with common-support and same-signal hashes within each model.
- Large signals, series and holdings stay in immutable artifacts; catalogs are GET-only.

## Portable runtime

- New profile config and validator resolve `local-apple-silicon`,
  `remote-linux-nvidia` or private `legacy-yilangliu`.
- Jobs persist execution profile and resolved release identity; retry inherits them;
  idempotency includes profile/release/session.
- Worker capability gate runs before claim. MPS/CUDA cannot silently fall back to CPU.
- Research subprocess receives an environment allowlist rather than the parent environment.
- Base remains explicit opt-in until its local/remote resource gate passes.

## Public data and weights

- Canonical file schema: instrument,timestamp,open,high,low,close with optional
  volume,amount; CSV and Parquet normalize to an identical canonical hash.
- Validators fail on duplicate/non-monotonic dates, invalid OHLC, non-finite values,
  timezone/calendar ambiguity, future dates or missing universe/PIT declarations.
- Tushare token is read only from environment or a 0600 file and never enters output.
- Official weight downloader supports Small default, Base opt-in, check/offline modes,
  allowlisted files, pinned revisions, tree hash, license inventory and canonical receipt.

## CLI

- `elanquant bootstrap --profile ... --release small|base [--dry-run]`
- `elanquant doctor --check-only`
- `elanquant smoke --fixture synthetic`
- `elanquant weights fetch|verify --release small|base [--offline]`
- `elanquant data import --source files|tushare ...`

## API/UI contract

- Execution profile availability is read from system status.
- Update-infer POST includes profile; job/run responses expose it.
- Public experiment and historical selectors filter to the four active IDs.
- Legacy strict-PIT evidence remains accepted by internal decoders and audit endpoints.
- Ranking exposes reference price and a formula-level explanation of ten-day predicted change.

## Testing

- Split golden tests: 101 rows, raw-overlap/effective-range proof, future perturbation,
  matured T+10 boundary and requested/actual backtest start.
- Runtime tests: profile/release compatibility, no fallback, idempotency, retry, env allowlist.
- Data/weight tests: CSV=Parquet canonical hash, corruption, offline verify, secret scan.
- Research tests: exact four cells, formal receipt, Top50/Top3 same-signal binding.
- Frontend: four public cells, retired strict hidden, metric definitions, six-nav shell,
  profile selection and legacy payload compatibility.
- Server-only: materialization, DDP training, inference/evaluation/backtest and release switch.
- Delivery: wheel/sdist contents, licenses, full backend/frontend gates, 1440/390/browser console.
