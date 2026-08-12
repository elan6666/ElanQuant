# Alternatives and Substitutes — 2026-08-13

Repository activity and community figures were checked against GitHub on
2026-08-13. Stars indicate reach, not correctness. ElanQuant copies no product
code or branding; it adapts small, license-safe interaction patterns.

| Product | Positioning / key pattern | License / pricing signal | Strength | Gap and ElanQuant response | Source |
|---|---|---|---|---|---|
| Kronos official demo | Foundation model fine-tune and simplified A-share backtest | MIT / open source | Author code and weights | Not production-ready and not strict-PIT; preserve the author baseline but add immutable admission and receipts | [GitHub](https://github.com/shiyu-coder/Kronos) |
| Microsoft Qlib | End-to-end quant research, experiment recorder and reports | MIT / open source | Mature run, model and portfolio abstractions | Defaults do not prove this dataset's PIT contract; adapt split-aware experiment lineage and support counts | [GitHub](https://github.com/microsoft/qlib) |
| MLflow | Parameter, metric, artifact and model-run tracking | Apache-2.0 / open source plus hosted offerings | Clear cross-run comparison | A separate service is unnecessary for one owner; implement the essential lineage in SQLite | [GitHub](https://github.com/mlflow/mlflow) |
| Evidently | Data-quality tests and immutable monitoring snapshots | Apache-2.0 / open source plus cloud | Makes data health visible | Avoid a new runtime; persist safe snapshot summaries and fail-closed states | [GitHub](https://github.com/evidentlyai/evidently) |
| VeighNa / vn.py | Event-driven trading apps, order/fill/position lifecycle | MIT / open source | Strong execution vocabulary | Broker gateways are out of scope; adapt explicit paper intent/fill/reject explanations | [GitHub](https://github.com/vnpy/vnpy) |
| QuantStats | Return analytics and tear sheets | Apache-2.0 / open source | Familiar portfolio evidence | Most metrics are invalid with one NAV point; expose evidence sufficiency and nulls instead of decorative numbers | [GitHub](https://github.com/ranaroussi/quantstats) |
| vectorbt | Fast portfolio/scenario analysis | Commons Clause / open-core restriction | Broad analysis vocabulary | Do not embed its code or encourage broad parameter mining; use only generic drawdown/turnover concepts | [GitHub](https://github.com/polakowo/vectorbt) |
| QuantConnect LEAN | Research/backtest/live execution engine | Apache-2.0 / open source plus cloud | Separates fees, slippage, fills and order events | Avoid the large engine and live broker surface; version paper execution assumptions | [GitHub](https://github.com/QuantConnect/Lean) |
| OpenBB | Provider-neutral financial research panels | AGPL-3.0 / open source plus enterprise | Strong source/as-of metadata presentation | Avoid AGPL code and platform scope; adapt compact evidence cards only | [GitHub](https://github.com/OpenBB-finance/OpenBB) |
| Notebook/scripts | Personal research substitute | Local effort | Fast to start | Weak durable jobs, provenance, paper ledger and owner UX; ElanQuant makes the evidence chain navigable | Internal substitute |

## Differentiation

ElanQuant is not a new forecasting architecture or broker terminal. It is the
auditable bridge from pinned Kronos behavior to strict-PIT A-share evidence:

`data snapshot → Small/Base experiment → online stock signal → frozen paper ledger`

The selected optimization wave therefore prioritizes six-cell split-aware
experiments, run comparison, data health, signal explanation and sample-aware
paper accounting. It deliberately excludes broker integration, another MLflow
server, third-party analytics runtimes, technical-indicator walls and claims of
investment effectiveness.
