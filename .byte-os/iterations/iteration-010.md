# Iteration 010 — Core completeness

- Added a hash-gated model-specific weekly ranking reader rather than reusing
  the Kronos daily score endpoint.
- Verified B2 and Kronos Base each use their own sealed score artifact while
  sharing the same weekly support.
- Added a UI regression that selects B2 and proves no online inference request
  is submitted.

Result: PASS.
