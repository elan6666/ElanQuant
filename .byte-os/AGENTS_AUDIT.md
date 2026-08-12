# AGENTS.md Audit

- Root AGENTS.md status: ready
- Module AGENTS.md files: none; current modules are small and root guidance is
  sufficient.
- Scoped command coverage: provisional backend/frontend/server commands are in
  root context and `CODEBASE_MAP.md`.
- Noise path coverage: source ignores and Claude deny filters cover generated
  research artifacts, dependencies, builds, and caches.
- LSP coverage: Pyright/Pylance and tsserver recorded.
- Subagent boundary coverage: read-only exploration, disjoint implementation,
  and read-only review boundaries recorded.
- Proposed updates: reconcile commands after scaffolding; consider module
  context only if server research scripts gain special invariants.
- Last reviewed: 2026-08-12
- Next review: after integrated server inference
- Owner/DRI: root integrator
