---
id: 014
title: Four-cell web product and metric semantics
status: complete
wave: 1
updated_at: 2026-08-14T07:50:00Z
owner_role: Product Designer
depends_on: []
start_directory: frontend
context_files: [AGENTS.md, CLAUDE.md, .byte-os/UX_SPEC.md]
agents_context_stack: [AGENTS.md]
subagent_policy: implementation_allowed
---

# Goal

Reduce the dashboard to decisions and understandable numbers while keeping
retired evidence compatible under the surface.

# OKR Link

KR5.

# Scope

`frontend/src/**` and frontend tests only.

# Non-Goals

No backend mock profile, no new page/framework, no deletion of decoder unions.

# Steps

## Step 1: Remove product noise
- Actions: delete Methods route/nav/page, simplify Hero and Jobs copy, move audit details into details.
- Verification: DOM copy/nav tests.
- Subagent: implementation_allowed.

## Step 2: Filter to four public cells
- Actions: Research and Historical selectors filter before fallback; honest empty state.
- Verification: six-cell/24-envelope inputs render exactly four public selectors.
- Subagent: implementation_allowed.

## Step 3: Explain metrics and execution location
- Actions: accessible metric definitions, reference-price formula, profile selector
  wired to real additive API contract and disabled unavailable states.
- Verification: semantic tests, keyboard, build.
- Subagent: implementation_allowed.

## Step 4: Responsive browser QA
- Verification: 1440x1000, 390x844, no page overflow/console errors, visible focus.
- Subagent: none.

# Scoped Commands

- Test: `npm test -- --run`
- Lint: `npm run lint`
- Build: `npm run build`

# Acceptance Criteria

Six navigation items; no Methods/AI slogans/ops prose; no visible Strict PIT;
all derived metrics state meaning/unit/denominator; profile selection is honest and usable.
