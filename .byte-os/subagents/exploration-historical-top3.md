# Historical Top3 exploration handoff

## Scope

Pinned Qlib TopkDropout semantics, existing sealed historical artifacts,
catalog/API isolation and responsive comparison UX.

## Files inspected

Official Kronos config/qlib test, pyqlib 0.9.7 signal strategy, ElanQuant
official-demo contracts/runners/catalog/API/frontend and current server receipts.

## Key facts

- Recommended exact variant is Top3/Drop1/Hold5 with all Qlib defaults locked.
- Signals/providers can and must be reused byte-for-byte; no inference is needed.
- The variant is post-hoc and non-selection/non-promotion for both splits.
- Qlib target cardinality can deviate under holding/tradability/cash constraints.
- A new exact 2×2 catalog must fail closed and never touch SQLite.

## Commands discovered

Server pytest/Ruff/Pyright/compile plus frontend Vitest/ESLint/build and an
independent artifact/paper/current-release audit.

## Safe edit boundaries

New isolated contract/runner/auditor files, API/settings, frontend source/tests,
docs and Byte artifacts. Never edit sealed runs, old catalogs, paper/storage or
official upstream.

## Risks and unknowns

Post-hoc concentration, Drop1 scale deviation, actual holding-count drift,
opened 2026 and legacy 2025 candidate semantics.

## Recommended next step

Create the comparison lock before any server Top3 result, then run two isolated
CPU-only Qlib backtests and publish catalog v4 only after independent audit.
