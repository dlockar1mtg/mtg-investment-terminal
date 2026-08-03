# Collector Long-Horizon Point-in-Time Feature Foundation

## Purpose

This foundation identifies the actual repository sources capable of supporting the Collector 365-day, 3-year, and 5-year models before derived features or coefficients are implemented.

## Core rules

- Every predictor must be observable on or before the historical decision cutoff.
- Realized outcomes remain separate from predictor fields.
- Missing features remain missing; they are not silently imputed or invented.
- Proxy features must be labeled as proxies.
- Every implemented feature must retain source lineage.
- No model, purchase, freeze, or UIP authorization is created by this foundation.

## Outputs

- Source catalog of CSV files and headers.
- Required raw-field coverage and candidate source paths.
- Point-in-time seed panel from the governed Phase 2A replay.
- Derived-feature implementation plan.
- Structural summary and strict audit.

## Feature groups

The contract covers identity, dates, prices, product age, returns, CAGR, volatility, drawdown, persistence, liquidity, scarcity, demand durability, reprint risk, net realizable value, and data quality.

## Transfer

Pre-Collector and Secret Lair reuse the point-in-time contract and governance structure. They require separate source mapping, feature construction, comparable groups, and calibration.

## Status

Shadow research only. No derived feature is considered implemented or certified until a source mapping and point-in-time calculation pass the associated audit.
