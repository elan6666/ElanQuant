# Iteration 004 — Evaluation-boundary correction

The first pass corrected the statistical meaning of the two historical splits.
Inspection of the pinned author training loop and sealed terminal logs proved
that training always ran 30 epochs, while the 2025 validation loss selected the
saved `best_model`. The 2025 period is therefore training validation and method
selection evidence, not an independent final evaluation.

The official-demo contracts now preserve the immutable 2025 receipt and add a
separate 2026 role for the already frozen Small official-style checkpoint and
predeclared mean/Top50/Drop5/Hold5 method. The new role is explicitly
non-selectable, records that the test data had already been viewed, and rejects
any attempt to change model, signal, strategy, execution parameters or mature
target support after the lock was written. No retraining, Small release change,
Base promotion or Top3 ledger write is part of this iteration.
