# App Architecture Exploration

## Scope

Read-only architecture for a single owner pressing an on-demand server job
button over SMBU VPN/SSH, with no brokerage integration.

## Files inspected

- `/Users/elan/Documents/量化/r16b_analysis_dashboard/package.json`
- Reusable patterns under `r16b_analysis_dashboard/src/components/` and
  `src/lib/`
- Existing dashboard delivery/review records and atomic publication script

## Key facts

- Use React/Vite, FastAPI, SQLite WAL, and a separate long-lived worker managed
  by user systemd. Redis/Celery/Kubernetes are unnecessary for v0.
- `POST /api/v1/jobs/update-infer` performs an idempotent DB insert and returns
  HTTP 202 immediately. The worker atomically claims the task, so browser/VPN
  disconnection cannot kill it.
- Bind the app to `127.0.0.1:8765` and reach it with an SSH local tunnel. Serve
  the built frontend from FastAPI for one same-origin service.
- Load GPU models in the inference subprocess only; release memory at process
  exit. Training is a separate CLI/job family and never part of the daily
  button.
- Polling every 2-5 seconds is sufficient. WebSockets add no required value.
- SQLite stores metadata/summaries; large immutable predictions live in ignored
  artifact directories and publish through temp file, fsync, and atomic rename.
- Manual updates mean skipped days must be explicit gaps. The system must not
  silently reconstruct decisions that the user never made.

## Proposed stages

`QUEUED → RESOLVING_SESSION → UPDATING_DATA → VALIDATING_DATA → INFER_SMALL →
INFER_BASE → SCORING → PAPER_LEDGER → SUCCEEDED`, with fail-closed `FAILED`.

## Safe edit boundaries

- New ElanQuant sources only.
- Reuse small generic ECharts/format/schema validation ideas; do not copy the
  old cohort-specific static JSON contract or monolithic application.
- No broker code, credentials, public bind, automatic VPN login, or training
  endpoint in v0.

## Verification required

- HTTP 202 returns quickly and duplicate clicks coalesce.
- Disconnect SSH immediately after submission; reconnect and observe completion.
- Incomplete/as-of/PIT data blocks output.
- Paper ledger updates atomically.
- API remains responsive while the worker runs.
- GPU memory is not resident before/after jobs.
- No secret or generated research artifact enters Git/log output.

## Risks and unknowns

- Reliable reboot survival may require administrator-enabled user linger.
- Interrupted jobs should be marked and explicitly retried, not guessed or
  automatically resumed across partial artifacts.

## Handoff

Adopt the minimal four-process boundary: browser, loopback API/static frontend,
durable worker, isolated GPU subprocess.
