# ElanQuant

## Concept

An auditable A-share Kronos research and simulated-trading web system. It
trains and compares official-aligned Small experiments and strict point-in-time
adaptations on the agreed extended daily dataset, then lets the owner manually
trigger data refresh and inference on the research server.

## Target user

The project owner, learning full-stack development while operating a personal,
research-only A-share model and paper-trading workflow.

## Core problem

Official Kronos examples demonstrate forecasting and backtesting but do not
provide a production-ready, strictly PIT A-share dataset, durable on-demand
job orchestration, or an auditable simulated account.

## Delivery format

- Browser UI reached from the Mac through SMBU VPN and an SSH tunnel.
- FastAPI service and background worker on the server.
- GPU-backed Kronos training and inference only on the server.
- Local GitHub repository contains source, tests, configs, and documentation;
  no market data, weights, runs, logs, credentials, or account information.

## Current stage

Byte Auto foundation.

## Success criteria

1. Small official zero-shot and A-share fine-tune experiments have frozen
   provenance and comparable evaluation receipts.
2. The Small strict-PIT variant uses the extended 2011-present dataset with
   causal membership, availability, split, context, and label boundaries.
3. The owner can press one button to update closed-session data and run
   inference; the server job survives browser or VPN disconnection.
4. The UI exposes results, data/model provenance, task state, rankings, and a
   simulated account without connecting a real brokerage account.
5. Server and local verification are recorded and reproducible.
