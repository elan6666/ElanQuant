# Product Specification — ElanQuant v0

## Positioning

An owner-operated, research-only A-share system that makes official Kronos
Small reproduction, strict-PIT adaptation, on-demand inference, and paper
trading understandable and auditable in one interface.

## Target users

- Primary: project owner, learning full-stack and quantitative research.
- Secondary: a technical reviewer checking data/model/execution evidence.

## Jobs to be done

1. Reproduce official behavior without confusing it with strict evidence.
2. Train Small against an extended, causal A-share dataset; defer Base.
3. Press one button after a close to update data and get a durable result.
4. Understand rankings, forecasts, limitations, simulated orders, and P&L.

## MVP

- Three-cell Small registry: zero-shot, official-style fine-tune, and strict-PIT
  fine-tune. Base is explicitly deferred.
- Extended CSI300 daily OHLCVA dataset and audit manifests.
- Manual `Update data and run inference` durable job; history/status/retry.
- Latest run, stock ranking/details, provenance and scoreability labels.
- RMB100k Top-3 paper account with frozen T intent and T+1 fill/reject ledger.
- Same-origin Chinese owner dashboard over VPN/SSH tunnel.

## Non-goals

- Real brokerage connectivity, credentials, orders, or recommendations.
- Automatic daily schedule or automatic VPN login.
- Intraday/high-frequency, leverage, shorting, options, futures, news/LLMs.
- Editing official model internals or claiming a new architecture.
- Calling viewed 2026 evidence an untouched final test.

## Requirements

- Server-only research workload and ignored generated artifacts.
- Every result binds code/data/config/model/tokenizer/membership hashes and seed.
- Duplicate clicks coalesce; accepted jobs survive UI/VPN disconnect.
- Data failure closes the run and never reuses an older recommendation as new.
- Paper orders cannot use T+1 state for T selection/sizing or post-failure refill.
- Model training is separate from the daily button.

## Acceptance criteria

1. All three Small cells have a terminal receipt or typed evidence-backed failure.
2. Extended data and strict splits pass PIT, membership, continuity, amount,
   adjustment, and latest-scoreable tests.
3. Button-to-result flow works and job state persists across disconnection.
4. Rankings and paper ledger reconcile and expose provenance/limitations.
5. Backend/frontend/server tests and a current ship review pass.
