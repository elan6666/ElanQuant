# Subagent Strategy and Ledger

## Mode

On for Byte Auto. All initial bounded tracks are complete and integrated. No
subagent owns active server credentials, downloads, GPU jobs, source merge, or
delivery verdict.

## Completed tracks

| Agent | Scope | Result |
|---|---|---|
| `app_architecture` | Durable API/Worker/SQLite/paper architecture and implementation | Main agent aligned API envelopes and added the real research pipeline. |
| `kronos_official` | Official repo/paper/weights/config evidence and frontend | Main agent removed the platform-only dependency and completed frontend checks. |
| `pit_simulation` | Strict PIT data and A-share simulated execution | Main agent added live limit constraints and server orchestration. |

Detailed handoffs remain under `.byte-os/subagents/`.

## Policy

Further implementation work is main-agent-only while server credentials, data,
and GPU jobs are active. Later review agents may receive read-only PIT,
security, UX, or delivery scopes. No agent may expose credentials, change VPN
routes, edit sibling legacy projects, or publish generated research artifacts.
