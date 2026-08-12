# ElanQuant Context

ElanQuant is a research-only A-share Kronos Small/Base and strict-PIT system.
Small remains the only online/paper release; Base is an isolated three-cell
research comparison and cannot be promoted implicitly.
Read `.byte-os/STATUS.md`, `.byte-os/CODEBASE_MAP.md`, `.byte-os/HARNESS.md`,
and the active plan before edits.

Source lives in `backend/`, `frontend/`, `scripts/`, `tests/`, and `docs/`.
Research workloads run only on the server under
`/data/yilangliu/a_share_research/elanquant`. Never commit data, weights,
checkpoints, generated results, logs, credentials, or account artifacts.

Use scoped backend/frontend commands from `AGENTS.md`. Do not edit pinned
official Kronos internals or sibling repositories. Real brokerage integration
is outside MVP.
