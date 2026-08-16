<p align="center">
  <img src="./assets/elanquant-logo.svg" width="320" alt="ElanQuant" />
</p>

<p align="center"><strong>An auditable A-share Kronos research console.</strong></p>

<p align="center">
  <a href="./README.en.md">English</a> · <a href="./README.md">简体中文</a>
</p>

<p align="center">
  <a href="#weight-only">Use public weights</a> ·
  <a href="#deep-reproduction">Deep reproduction</a> ·
  <a href="./docs/OPERATIONS.md">Operations</a> ·
  <a href="./docs/DATA_POLICY.md">Data policy</a>
</p>

> Research and paper trading only. ElanQuant has no broker connection, does not
> place real orders, and is not investment advice.

## What ElanQuant is

ElanQuant keeps three things deliberately separate:

1. **Model evidence** — a pinned Kronos source revision, tokenizer/predictor
   identities, configuration, data manifest and evaluation receipt.
2. **Where inference runs** — Apple Silicon locally or Linux/NVIDIA remotely.
3. **What a result may do** — Small can publish a paper-account decision only
   after release admission; Base is research-only and never mutates the paper
   ledger.

The public dashboard exposes four active research cells:

| Size | Zero-shot | Official-style fine-tuning |
| --- | --- | --- |
| Small | public Kronos Small weights | official training flow with user-provided A-share data |
| Base | public Kronos Base weights | official training flow with user-provided A-share data |

Retired Strict-PIT receipts remain auditable artifacts, but are not selectable
in the product UI and are never silently reused as an active model.

## Supported inference

| Layer | Supported choices | Practical rule |
| --- | --- | --- |
| Model release | `small`, `base` | Small is the default. Base is explicit and remains research-only. |
| Execution profile | `local-apple-silicon`, `remote-linux-nvidia` | Profiles identify hardware/runtime; they do not change model evidence. |
| Device | MPS / CUDA after capability checks | CPU is for contract checks, not a recommended research workload. |
| Online paper publication | admitted Small release only | A frozen signal day is published once; reruns cannot append orders. |

The currently deployed service reports its active release, device and profile
at `GET /api/v1/system/status`. A UI instance can submit only to the profile it
was configured for; it does not pretend that separate machines are one shared
runtime.

## Choose your path

| Choose this path | You want to | You need | You get |
| --- | --- | --- | --- |
| [Use public weights](#weight-only) | predict or inspect a stock with the published Kronos weights | Python, a supported device, and your own daily bars/calendar | a single-instrument zero-shot forecast and a complete local receipt |
| [Deep reproduction](#deep-reproduction) | rebuild the four-cell experiment and Top50/Top3 studies | a licensed PIT dataset, Linux/NVIDIA, Qlib and long-running compute | a new immutable data/training/evaluation/backtest evidence chain |

Path A is for a user who wants to use the weights. Path B is for a research
user who wants to reproduce the method. Do not take a Path A forecast as a
reproduction of the historical study.

<a id="weight-only"></a>

## Path A — use public weights for prediction or analysis

**Use this when you only need an auditable zero-shot forecast for your own
stock data.** It does not train a model, rebuild the CSI300 study, create a
paper order or claim investment performance.

| Step | What happens | What it does not do |
| --- | --- | --- |
| Install and synthetic check | verifies CLI, data contract and frontend | downloads no market data or model |
| Bootstrap | fetches and SHA-checks public tokenizer/Small/Base files | does not create an A-share fine-tuned checkpoint |
| Data import | validates your CSV/Parquet and writes a receipt | does not certify your vendor data as point-in-time |
| Zero-shot inference | forecasts one instrument from 90+ historical rows | does not rank CSI300 or backtest a trading strategy |

### 1. Clone and install

```bash
git clone https://github.com/elan6666/ElanQuant.git
cd ElanQuant

python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,repro]'

npm --prefix frontend install
```

### 2. Verify the portable contract with synthetic data

This step downloads no market data and does not run a Kronos model.

```bash
elanquant data import \
  --input examples/data/synthetic_daily.csv \
  --output .elanquant/data/synthetic.csv \
  --calendar synthetic-weekday \
  --universe-policy synthetic-fixture \
  --pit-declaration research-demo-only \
  --source-license repository-fixture

elanquant doctor --check-only --scope capability \
  --profile local-apple-silicon --release small --device mps
elanquant smoke --fixture synthetic \
  --profile local-apple-silicon --release small --device mps

python -m pytest -q
npm --prefix frontend test -- --run
npm --prefix frontend run build
```

`smoke` proves the runtime and receipt boundary only. It is not an A-share
prediction, backtest or performance claim.

### 3. Fetch public Kronos weights

Install the inference extra, inspect the plan, then fetch the selected public
release. The command writes SHA-256 receipts for every downloaded file.

```bash
python -m pip install -e '.[repro,inference]'

elanquant bootstrap --profile local-apple-silicon --release small --dry-run
elanquant bootstrap --profile local-apple-silicon --release small

# Linux/NVIDIA example; Base is an explicit choice.
elanquant bootstrap --profile remote-linux-nvidia --release base
```

The upstream source is pinned separately:

```bash
git clone https://github.com/shiyu-coder/Kronos.git .elanquant/upstream/Kronos
git -C .elanquant/upstream/Kronos checkout 67b630e67f6a18c9e9be918d9b4337c960db1e9a
test "$(git -C .elanquant/upstream/Kronos rev-parse HEAD)" = \
  67b630e67f6a18c9e9be918d9b4337c960db1e9a
```

### 4. Import your own market data

ElanQuant accepts CSV or Parquet with the required schema below. It does **not**
ship market data, credentials, trained checkpoints or a vendor token.

| Field | Required | Notes |
| --- | --- | --- |
| `instrument` | yes | stable code, e.g. `000001.SZ` |
| `timestamp` | yes | an exchange session timestamp |
| `open`, `high`, `low`, `close` | yes | positive finite values |
| `volume`, `amount` | optional | non-negative; filled with zero when absent |

```bash
elanquant data import \
  --input /path/to/your_daily_bars.parquet \
  --output .elanquant/data/a-share.parquet \
  --calendar your-exchange-calendar-v1 \
  --universe-policy your-pit-universe-policy-v1 \
  --pit-declaration "membership known by the next session" \
  --source-license "your-data-license"
```

The import rejects duplicate instrument/session rows, future timestamps,
non-finite values, invalid OHLC relationships and negative volume/amount. Its
sidecar receipt binds both source and normalized output hashes.

### 5. Run one zero-shot forecast

Create `future-sessions.csv` from your actual exchange calendar — do not use
weekday arithmetic as a trading calendar.

```text
session
2026-08-14
2026-08-17
...
```

```bash
elanquant infer zero-shot \
  --input .elanquant/data/a-share.parquet \
  --instrument 000001.SZ \
  --future-sessions future-sessions.csv \
  --release small \
  --device mps \
  --output .elanquant/forecasts/000001.SZ.csv \
  --dry-run
```

Remove `--dry-run` only after checking the plan. The result records input,
output, upstream, weights and execution identities. Its displayed 10-day value
is `mean(next_10_predicted_closes) / current_close - 1`: not a probability and
not realised return.

<a id="deep-reproduction"></a>

## Path B — deep reproduction

**Use this only when you intend to rebuild the research evidence chain.** It
requires separately licensed historical data and a Linux/NVIDIA research host.
It is intentionally not a one-command download: data availability, PIT
membership history, vendor revisions and licences must be declared rather than
hidden.

There are two honest reproducibility levels:

- **Portable code reproduction**: the quick-start above reproduces the CLI,
  contracts, synthetic fixture, frontend and public-weight verification on a
  clean machine.
- **Research-result reproduction**: requires a licensed, point-in-time data
  snapshot and suitable Linux/NVIDIA hardware. It recreates every receipt from
  the same input bytes; it cannot promise identical results from a different
  vendor revision or a different point-in-time membership history.

The official-demo split is recorded as raw slices, with effective windows
audited independently:

| Slice | Raw range | Purpose |
| --- | --- | --- |
| Train | 2011-01-01 – 2022-12-31 | Tokenizer and Predictor training |
| Validation | 2022-09-01 – 2024-06-30 | per-epoch validation loss / checkpoint selection |
| Rolling test | 2024-04-01 – frozen latest session | mature prediction evaluation |
| Backtest | requested from 2024-07-01 | Top50/Drop5/Hold5 and Top3/Drop1/Hold5 |

Raw slices overlap only to provide lookback context. The dataset audit proves
the effective 101-row training/validation windows and 90-session inference
context do not cross the relevant boundary. Once rolling-test results have
been opened, they are marked `TEST_VIEWED`, descriptive only, and are not valid
for model or strategy promotion.

For the exact server-only workflow, including immutable run IDs, admission,
training, four-cell matrix compilation, locked signal generation, Qlib
backtests and release auditing, follow [the full reproduction guide](./docs/REPRODUCTION.md).

## Read the dashboard correctly

- **RankIC**: rank correlation between a prediction and mature 10-day actual
  return; near zero means weak ordering ability.
- **Pearson IC**: linear correlation between predicted and mature actual return.
- **Top10 actual return**: mean mature outcome of the ten highest-ranked names
  each eligible session.
- **Historical cumulative return**: arithmetic sum of daily returns in the
  official Qlib-style report; it is not a live account NAV.
- **Input completeness**: the share of required admission inputs present; it is
  not confidence.

## Verification commands

```bash
python -m pytest -q
ruff check backend scripts tests
pyright --pythonpath .venv/bin/python backend/src scripts/research
python -m compileall -q backend/src tests scripts

npm --prefix frontend test -- --run
npm --prefix frontend run lint
npm --prefix frontend run build
```

## Data, weights and licensing

Kronos source, its public tokenizer/Small/Base weights and market data have
separate licences. MIT licensing for ElanQuant source does not grant the right
to redistribute third-party weights, vendor data, user credentials or
ElanQuant fine-tuned checkpoints. See [DATA_POLICY.md](./docs/DATA_POLICY.md)
and [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md).

## License

ElanQuant source is released under the [MIT License](./LICENSE).
