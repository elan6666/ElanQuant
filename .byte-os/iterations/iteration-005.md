# Iteration 005 — Dual-split evidence product and chart repair

The second pass changed the historical research page from a single ambiguous
2025 result into an exact two-entry evidence view. Its first draft called 2026
a frozen final sample-out evaluation and kept 2025 behind an explicit
checkpoint-selection validation tab. The subsequent leakage review rejected
that claim: the delivered page calls 2026 an opened out-of-sample diagnostic
and states that it cannot be used for further selection or tuning.

The clipped return chart was traced to an SVG replaced element retaining its
intrinsic minimum height inside a flex card. The chart now uses an explicit
grid with a shrinkable plot row, resets the SVG minimum height, and reserves a
separate legend/caption row. This keeps the full curve, negative range and zero
line inside the card at desktop and mobile widths. API decoders and component
tests fail closed on invalid split roles, missing entries and inconsistent
series lengths.
