# Iteration 006 — Leakage review and corrected opened diagnostic

The third pass responded to an independent statistical review rather than
shipping a cosmetically correct but causally invalid chart. The first 2026
strategy artifact required each T-day candidate to retain ten future symbol
rows. That conditioned the T universe on future membership/data availability,
and a small subset used future symbol observations instead of global exchange
timestamps. The artifact and its receipts remain preserved as an opened
diagnostic, but it was removed from the active catalog and never used to select
a model, signal or parameter.

The corrected candidate builder now requires only information known at T: the
symbol must be present at T and have a complete context over the preceding 90
global exchange sessions. Forecast timestamps are the next ten global exchange
sessions; future symbol membership and future symbol-row availability are not
read. Golden tests prove that a symbol disappearing immediately after T remains
eligible at T, while a missing historical context session excludes it.

Because the 2026 window was already opened, the corrected result is named an
`opened out-of-sample diagnostic`, not a new final/blind/untouched test. The
next true final test is reserved for a future window that has not been viewed.
The original Top3 paper product, Small release and immutable 2025 validation
evidence remain unchanged.
