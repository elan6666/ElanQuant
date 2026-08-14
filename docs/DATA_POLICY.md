# Data Policy

ElanQuant source code is MIT-licensed. That license does not grant rights to
market data, provider accounts, or model checkpoints trained from third-party data.

## What the repository contains

- Source code, schemas, configs and tests.
- A small synthetic fixture under its own repository license.
- Download instructions and pinned identities for official Kronos weights.
- Receipt formats describing data without containing credential bytes.

## What the repository does not contain

- Tushare or other provider data.
- User CSV/Parquet files, tokens, databases, predictions, reports or checkpoints.
- The owner's proxy credentials, campus server address or private deployment config.

## User-owned file data

`elanquant data import` accepts CSV or Parquet only after the user supplies a
calendar, universe policy, point-in-time declaration and source-license label.
The command validates schema/OHLC/timestamps and writes a canonical data hash.
Passing validation proves structural consistency, not that the user's source is
legally redistributable or historically point-in-time.

Required columns:

```text
instrument,timestamp,open,high,low,close
```

Optional columns are `volume` and `amount`; missing optional values become zero.

## Tushare-compatible data

The private server workflow creates clients only through an approved
`get_pro()` adapter and reads credentials outside the repository. Public users
must supply their own authorized adapter/account and comply with the provider's
terms. Tokens must never be passed on a command line, printed or stored in receipts.

The owner's tutorial-compatible proxy uses plain HTTP. Private receipts disclose
that transport limitation. It is not a public default and its outputs are not distributed.

## Fine-tuned checkpoints

ElanQuant does not publish A-share fine-tuned weights until the data license is
reviewed and positively permits the intended redistribution. Reproduction from
user-owned licensed data remains available even when checkpoint hosting is disabled.

## Research boundary

ElanQuant is for research and education, does not connect to a broker and does
not provide investment advice.
