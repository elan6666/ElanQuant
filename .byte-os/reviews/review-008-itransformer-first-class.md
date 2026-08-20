---
created_at: 2026-08-20T20:45:00+08:00
verdict: ship
---

# Review 008 — iTransformer B2 first-class research surface

Verdict: **SHIP**

## Evidence

- The B2 model is exposed through a separate, receipt-bound weekly comparison
  catalog, not through the daily Kronos job or paper-account path.
- The live comparison catalog verifies two model families, six Top1/Top3/Top50
  results, common weekly support, and 17 weekly anchors. B2 uses 80 historical
  sessions; Kronos Base uses 90. Neither window is coerced into the other.
- The new ranking endpoint rehashes the prediction artifact, rejects duplicate
  `(anchor, instrument)` rows, checks the exact common support count, and
  returns 280 B2 candidates for the final sealed anchor, 2026-07-24.
- Server verification: 160 pytest passed, one skipped; Ruff and compileall
  passed. Frontend verification: 28 tests, ESLint and production build passed.
- Logical SQLite hash before and after comparison GETs was identical:
  `4af8174c6642a8066df191fc11636be929a3fd70def082e078fbc3c4e6e167b3`.

## Boundary

The imported B2 results are viewed, strict-weekly research evidence. They do
not create a job, recommendation, paper order or current-day ranking. A fresh
B2 update requires a new admitted D0/calendar and a separately sealed run.
