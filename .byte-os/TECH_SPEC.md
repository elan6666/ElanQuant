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

Jobs/events; data snapshots with safe health summaries; model versions;
run-bound split evaluations; inference runs; stock scores; recommendation
sets/items; one publication per signal session; intent decisions; paper
accounts, positions, orders, fills and portfolio snapshots. Large paths are
immutable artifacts referenced by hash.

## API

- `GET /api/v1/health`, `/system/status`
- `POST /api/v1/jobs/update-infer` -> 202/idempotent ID
- `GET /api/v1/jobs`, `/jobs/{id}`; `POST /jobs/{id}/retry`
- `GET /api/v1/research/experiments` for the sealed six-cell catalog
- `GET /api/v1/runs`, `/runs/latest`, `/runs/{id}`, scores, diff and data health
- `GET /api/v1/paper/account`, orders, NAV and evidence-aware summary

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
- Frontend: schema rejection, live backend-shaped envelopes,
  empty/running/failure/success, keyboard ranking and responsive build.
- E2E: submit, disconnect, reconnect, completion; GPU released after job.
