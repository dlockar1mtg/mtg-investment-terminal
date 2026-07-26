# Phase 10.16 — MTG Domain Production Closeout

## Purpose

Close MTG as an independent source system while assigning all cross-domain allocation and scheduling authority to the Universal Investment Platform (UIP).

## Governance

- MTG owns data collection, certification, domain forecasts, holdings, transaction history, and domain feasibility.
- UIP owns monthly budget selection, cross-domain ranking, capital allocation, cash decisions, scheduling, and orchestration.
- MTG does not self-assign a recurring monthly budget.
- No scheduled workflow is added in this phase.

## Production capabilities

1. Idempotent purchase recording and holdings updates.
2. Auditable MTG transaction ledger.
3. UIP-assigned carry-forward capital tracking.
4. Standardized `uip-domain-opportunity-v1` export.
5. Whole-unit purchase increments and maximum feasible allocation.
6. Explicit allocation and scheduling authority fields.
7. Fail-closed status when decisions or purchase planning are unavailable.

## Primary outputs

- `data/terminal2/portfolio_holdings.csv`
- `data/terminal2/mtg_transaction_ledger.csv`
- `data/terminal2/mtg_carry_forward.json`
- `data/operations/mtg_marketplace/mtg_uip_domain_export.json`

## UIP contract

Each opportunity includes identity, signal, eligibility, allocation score, confidence, unit price, minimum allocation, allocation increment, maximum units, maximum allocation, whole-unit requirement, risk evidence, and policy version.

UIP may allocate zero capital, one or more whole-unit increments, or retain the entire budget as cash. MTG may not override the UIP allocation.
