# Product Specification — ElanQuant v0

## Positioning

An owner-operated, research-only A-share system that makes official Kronos
Small/Base comparison, strict-PIT adaptation, on-demand inference, and paper
trading understandable and auditable in one interface.

## Target users

- Primary: project owner, learning full-stack and quantitative research.
- Secondary: a technical reviewer checking data/model/execution evidence.

## Jobs to be done

1. Reproduce official behavior without confusing it with strict evidence.
2. Compare Small and Base against the same extended, causal A-share dataset.
3. Press one button after a close to update data and get a durable result.
4. Understand rankings, forecasts, limitations, simulated orders, and P&L.

## MVP

- Six-cell Small/Base registry: zero-shot, official-style fine-tune, and
  strict-PIT fine-tune for each model size. Base is research-only and cannot
  silently replace the admitted Small online model.
- Extended CSI300 daily OHLCVA dataset and audit manifests.
- Manual `Update data and run inference` durable job; history/status/retry.
- Split-aware experiments, run history/diff, data health, stock ranking/details,
  provenance and scoreability labels.
- RMB100k Top-3 paper account with frozen T intent and T+1 fill/reject ledger.
- A separate historical official-demo-method research page: Small official-ft,
  standardized-space signals, sample-count 5, Top-50, Drop-5 and minimum hold
  5. It separates 2025 training validation from a corrected, already-opened
  2026 out-of-sample diagnostic; both
  are artifact-only and cannot create paper orders.
- Same-origin Chinese owner dashboard over VPN/SSH tunnel.

## Non-goals

- Real brokerage connectivity, credentials, orders, or recommendations.
- Automatic daily schedule or automatic VPN login.
- Intraday/high-frequency, leverage, shorting, options, futures, news/LLMs.
- Editing official model internals or claiming a new architecture.
- Calling the opened 2026 result blind/final, or reusing it to tune/select a
  later version. The next true final test requires a future untouched window.

## Requirements

- Server-only research workload and ignored generated artifacts.
- Every result binds code/data/config/model/tokenizer/membership hashes and seed.
- Duplicate clicks coalesce; accepted jobs survive UI/VPN disconnect.
- Data failure closes the run and never reuses an older recommendation as new.
- Paper orders cannot use T+1 state for T selection/sizing or post-failure refill.
- A signal session has exactly one frozen paper publication; force reruns remain
  research-only and expose their skipped-publication reason.
- Model training is separate from the daily button.
- Top3 online paper trading and the official-demo historical version never share
  orders, positions, NAV, strategy identity or mutation endpoints.

## Acceptance criteria

1. All six Small/Base cells have a terminal receipt or typed evidence-backed failure.
2. Extended data and strict splits pass PIT, membership, continuity, amount,
   adjustment, and latest-scoreable tests.
3. Button-to-result flow works and job state persists across disconnection.
4. Rankings and paper ledger reconcile and expose provenance/limitations.
5. Backend/frontend/server tests and a current ship review pass.
