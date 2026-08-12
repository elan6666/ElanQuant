# PIT and Simulation Exploration

Scope: strict split, membership, availability, adjustment, T/T+1 execution,
paper account, and reusable read-only contracts in sibling seven-model code.

Critical finding: never use T+1 buyability to modify T selection and never size
orders from known T+1 open. Freeze T-known order intent; T+1 can only fill or
reject without replacement. Concepts from raw manifests, availability guards,
dynamic membership, execution receipts, fees, and ledger invariants may be
ported, but sibling source/results remain unchanged.
