# Technical Specification

## Architecture

- React/TypeScript/Vite frontend built and served by FastAPI.
- FastAPI loopback service on `127.0.0.1:8765`.
- SQLite WAL metadata database with busy timeout and atomic portfolio commits.
- Independent worker atomically claims queued jobs; GPU pipeline runs in child
  process and publishes immutable artifacts atomically.
- Access only with EasyConnect plus SSH local forwarding.

## Backend modules

`api`, `orchestration`, `pipelines`, `storage`, and `settings`. Research
contracts plus training/data CLIs live under `scripts/`.

## Data model

Jobs/events; data snapshots; model versions; inference runs; stock scores;
recommendation sets/items; paper accounts; positions; order intents; fills;
portfolio snapshots. Large paths are immutable artifacts referenced by hash.

## API

- `GET /api/v1/health`, `/system/status`
- `POST /api/v1/jobs/update-infer` -> 202/idempotent ID
- `GET /api/v1/jobs`, `/jobs/{id}`; `POST /jobs/{id}/retry`
- `GET /api/v1/runs/latest`, `/runs/{id}`, scores and stock detail
- `GET /api/v1/paper/account`, orders, NAV

## Research protocols

- Pin official upstream/HF revisions and hashes.
- Separate official-style A-share and strict-PIT config namespaces. Neither is
  mislabeled as an exact qlib backtest reproduction.
- Strict split by complete target ranges; tokenizer/scaler/predictor fit only on
  training data. Online latest anchors never enter metrics before maturation.
- Main signal inverse-transforms predicted closes then implements the paper
  ten-day mean-return formula with T=.6, top-p=.9, N=10.

## Security and operations

- No public bind, broker code, credentials, secrets in logs, or generated
  artifacts in Git.
- Approved server data client only; source token remains server-only.
- user-systemd services with `Linger=yes`; retain an honest warning until the
  current submit/disconnect/reconnect E2E passes.

## Testing

- Unit: split, hashes, job state/idempotency, scoring, board lots, costs.
- Integration: 202 response, worker claim/recovery, incomplete data fail-close,
  paper transaction and duplicate-date protection.
- Research: official pin/hash, future perturbation, membership, adjustment,
  tokenizer fit boundary, common-support metrics.
- Frontend: schema rejection, empty/running/failure/success and responsive build.
- E2E: submit, disconnect, reconnect, completion; GPU released after job.
