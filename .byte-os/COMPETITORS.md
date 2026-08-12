# Alternatives and Substitutes — 2026-08-12

| Product | Positioning | Strength | Gap for ElanQuant | Source |
|---|---|---|---|---|
| Kronos official demo | Model fine-tune and simple A-share backtest | Author code and weights | Explicitly not production-ready; non-strict split/signal issues | [GitHub](https://github.com/shiyu-coder/Kronos) |
| Microsoft Qlib | Quant research and portfolio framework | Mature data/model/backtest abstractions | Does not by itself guarantee this project's PIT/provenance contract | [Docs](https://qlib.readthedocs.io/) |
| Broker QMT/CATS/PB | Execution and broker-side quant tools | Direct trading and broker controls | Account permissions/compliance; outside research-first MVP | [CITIC disclosure](https://www.citics.com/newsite/xxgs/qdxx/) |
| Notebook/scripts | Personal research substitute | Fast to start | Weak durable jobs, provenance, paper ledger, and owner UX | Internal substitute |

## Differentiation

ElanQuant is not a new forecasting architecture or broker terminal. It is the
auditable bridge from pinned official Kronos behavior to strict-PIT A-share
evidence, a durable one-button inference workflow, and a truthful simulated
account suitable for learning full-stack engineering.
