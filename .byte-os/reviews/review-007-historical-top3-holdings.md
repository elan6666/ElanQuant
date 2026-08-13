---
created_at: 2026-08-13T21:20:00+08:00
verdict: ship
---

# Review 007 — Historical Top3 and holdings

Verdict: **SHIP**

## Evidence

- Exact four cells: 2025/2026 × Top50/Top3; historical Top3 is post-hoc,
  non-selection, non-promotion and explicitly not the online paper account.
- Catalog v5 and all holdings receipts/artifacts pass canonical hash, schema,
  support, finite-value, duplicate, empty-session and permission gates.
- Top50 replay checked 40 metrics per split; maximum absolute differences were
  below 4e-15 against a 1e-12 gate.
- Holdings endpoints expose 233/233 and 137/137 sessions; latest actual counts
  are 51, 4, 55 and 4, with the Qlib target-cardinality caveat visible.
- SQLite full-table logical hashes are unchanged across historical GETs;
  `releases/current` remains Small r2.
- API/Worker are active and loopback-only; hostile Host is rejected.
- Desktop/default and 390 px browser checks show the correct four-cell UI,
  holdings interactions, no page overflow and no console warnings/errors.

## Interpretation

The Top3 sensitivity result is materially worse than Top50 in both windows.
It is useful negative evidence, not a strategy promotion result.
