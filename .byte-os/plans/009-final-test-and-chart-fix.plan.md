---
id: 009
title: Corrected opened 2026 diagnostic and historical chart repair
status: complete
owner: root integrator
implementation_allowed: true
depends_on: [008]
---

# Outcome

Repair the clipped historical return chart and correct the evaluation boundary:
2025 is the training-validation/checkpoint-selection split. The first 2026
artifact revealed future-support-conditioned eligibility and is retained only
as a diagnostic. A corrected 2026 run uses only T-known eligibility and global
exchange timestamps; because the window is opened, it is not relabeled blind or
final. A future untouched window is reserved for the next true final test.

# Write scope

- `backend/src/elanquant/contracts/official_demo.py`
- `backend/src/elanquant/api/app.py`
- `frontend/src/{api.ts,types.ts,App.tsx,styles.css}`
- `frontend/src/pages/HistoricalBacktestPage.tsx`
- `frontend/src/**/*test*`
- `scripts/server/*official_demo*`
- `tests/test_*official_demo*`
- `docs/{RESEARCH_PROTOCOL,RESULTS_20260812,OPERATIONS}.md`
- `.byte-os/` lifecycle, review, iteration and delivery artifacts

# Non-goals

- No retraining, checkpoint replacement, Base promotion, Top3 change, broker,
  schedule, SQLite migration, paper order, recommendation or portfolio write.
- Never use 2026 metrics to choose a model, signal or parameter.
- Never overwrite the immutable 2025 validation artifacts.
- Do not relabel 2026 as still blind after its one-time result is opened.

# Implementation

1. Generalize the sealed official-demo signal/provider/backtest contracts to
   admit exactly two active roles: checkpoint-selection validation and a
   corrected opened out-of-sample diagnostic.
2. Preserve the existing 2025 receipt and add a new immutable 2026 receipt for
   the frozen Small official-ft checkpoint, mean-primary four-signal protocol,
   Top50/Drop5/Hold5 strategy and identical execution constants.
3. Make the catalog and GET-only API expose both entries by exact allowlisted
   IDs, rechecking canonical receipt and artifact hashes on every read.
4. Default the historical page to the corrected opened 2026 diagnostic, retain an explicit 2025
   training-validation tab, and disclose that 2026 is opened and cannot be used
   for subsequent selection.
5. Repair the SVG flex sizing so all points and the negative range render inside
   the chart viewport at desktop and mobile widths.
6. Run the 2026 workload only on the server in an immutable run directory, audit
   paper-table non-mutation, publish the catalog atomically, deploy and QA.

# Acceptance criteria

1. Training evidence proves 2025 validation loss selected `best_model`; product
   copy never calls 2025 a final or untouched evaluation.
2. The 2026 receipt binds the pre-existing frozen checkpoint, matrix, data,
   provider, benchmark, code, dependency and strategy hashes and is
   `selection_eligible=false`.
3. 2026 signals contain only the test partition; T-day eligibility uses only a
   complete prior 90-session global context, while forecast timestamps are the
   next ten global exchange sessions and never require future symbol presence.
   The result is labelled opened diagnostic and cannot feed any selector.
4. Historical GET endpoints remain GET-only and do not mutate jobs, runs,
   recommendations, SQLite paper tables or the Small release symlink.
5. The page defaults to 2026, clearly separates it from 2025, and shows both
   metrics/curves without calling standardized scores forecast returns or NAV.
6. All 233 validation points and every 2026 test point render across the full
   chart width; negative values and zero baseline are visible without clipping
   at 1440x1000 and 390x844.
7. Backend/frontend tests, Ruff, Pyright, compileall, build, audit, systemd and
   live API/browser checks pass; an independent review reports no P0/P1.

# Verification

- Server: `app-venv/bin/python -m pytest -q`
- Server: `app-venv/bin/ruff check backend/src scripts tests`
- Server: `app-venv/bin/pyright backend/src scripts/research`
- Server: `app-venv/bin/python -m compileall -q backend/src scripts tests`
- Frontend: `npm --prefix frontend test -- --run`
- Frontend: `npm --prefix frontend run lint`
- Frontend: `npm --prefix frontend run build`
- Receipt/catalog audit and before/after paper-table hash comparison
- Live GET/405/security checks and desktop/mobile visual QA
