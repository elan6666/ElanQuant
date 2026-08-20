# Subagent Strategy

## Current run

- Mode: on
- Integrator: root
- Date: 2026-08-14

## 2026-08-20 model-family exploration

| Agent | Scope | Result |
|---|---|---|
| comparison_contracts | Server B2 B2 source/artifact feasibility | confirmed sealed B2 has 17 mature weekly anchors through 2026-07-24 and 80-session inputs; no current D0 exists for a fresher result |
| comparison_frontend | Current frontend model/selector constraints | confirmed Jobs, matrix, historical and ranking hard-code Kronos and need independent family-aware contracts |
| elanquant_integration | Backend/API safety boundary | confirmed existing Kronos historical and online ranking APIs must remain separate from B2 artifact-only evidence |

## Exploration completed

- `base_receipt_audit`: official split/training/evaluation/backtest migration.
- `live_product_review`: portable runtime, data/weight/bootstrap and packaging audit.
- `design_qa_review`: web simplification, metric semantics and responsive acceptance.

All exploration was read-only. The root resolved one conflict: despite legacy
six-cell evidence, the new active v1 matrix is exactly four cells
(Small/Base x zero-shot/official-ft); no new strict-PIT training is in scope.

## Implementation ownership

| Agent | Plan | Allowed write scope | Non-goals |
|---|---|---|---|
| base_receipt_audit | 011 | new versioned official-split research contracts/scripts/configs and focused research tests | no backend API/frontend/docs; no server execution; no strict-PIT v1 cell |
| live_product_review | 012 | backend runtime/settings/jobs/API/database, deploy profile templates and focused backend tests | no frontend/research scripts/README; no server restart |
| design_qa_review | 014 | frontend/src and frontend tests | no backend/API invention; no README |
| root | 013 + integration | CLI public data/weights/bootstrap/package/docs/Byte OS, merge, server execution and delivery | no destructive artifact deletion |

## Handoff contract

Every agent returns Scope, Allowed files, Files inspected, Files changed,
Verification, Result, Risks and Handoff. Root reviews diffs and reruns integrated gates.
