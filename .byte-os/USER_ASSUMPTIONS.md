# User Assumptions

## Facts supplied by the user

- The product is for the project owner and doubles as a zero-to-full-stack
  learning project.
- Training must run on the `yilangliu` research server.
- Small, strict PIT, and the previously agreed extended dataset are in scope.
- On 2026-08-13 the owner first deferred Base training, then explicitly
  reactivated the exact Base zero-shot/official-style/strict-PIT comparison.
- Real brokerage-account testing is not in scope.
- Daily automatic refresh is not desired; a button should update data and run
  inference.
- The Mac needs SMBU EasyConnect to reach the server.

## Product assumptions

- One authenticated owner is sufficient; multi-tenant accounts are unnecessary.
- A paper account with configurable initial cash is sufficient for MVP.
- Daily close data produces a signal for the next trading session, never a
  same-close fill.
- Auditability and learning clarity are more important than minimizing clicks.

## Unknowns to resolve with evidence

- Exact data coverage and latest scoreable date.
- How the three Base tracks compare with Small on frozen common support.
- Whether Base should ever be promoted; the current authorization is research
  comparison only and Small remains the online/paper model.
- Whether a future broker exposes an approved API; this does not affect MVP.
