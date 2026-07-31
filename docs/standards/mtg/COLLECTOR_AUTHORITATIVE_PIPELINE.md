# Collector Authoritative Production Pipeline

## Status

Phase 8.2.8 implementation baseline. This document identifies the intended authoritative Collector lane and the required certification boundary. It does not authorize forecasts or purchases.

## Governing owner

Devon Lockard is the designated owner. Material changes require explicit owner approval under `config/mtg/governance/collector_production_change_control_v1.json`.

## Authoritative stages

1. Dynamic product discovery and admission
2. Canonical product registry
3. Current-price collection and reconciliation
4. Historical ledger construction and certification
5. Supply, demand, liquidity, and comparable evidence normalization
6. Forecast-method routing
7. Comparable selection where required
8. Method-aware forecast generation
9. Economic and semantic diagnostics
10. Purchase analysis
11. MTG export and UIP reconciliation
12. Owner acceptance and certification

## Current authoritative inputs

- `data/product_master/investment_products.csv`
- `data/product_master/product_master_model_input.csv`
- `data/operations/collector_booster_history_certification/candidate_v1_0_0/collector_history_product_certification.csv`
- `data/operations/collector_evidence_normalization/candidate_v1_0_0/collector_normalized_evidence.csv`
- `data/operations/collector_forecast_method_routing/candidate_v1_0_0/collector_forecast_method_routes.csv`
- `data/operations/collector_comparable_selection/candidate_v1_0_0/collector_comparable_target_status.csv`
- `data/operations/collector_comparable_selection/candidate_v1_0_0/collector_selected_comparables.csv`

## Current authoritative producers

- `scripts/run_collector_booster_auto_admission.py`
- `scripts/certify_collector_booster_history.py`
- `scripts/normalize_collector_evidence.py`
- `scripts/route_collector_forecast_methods.py`
- `scripts/select_collector_comparables.py`
- Phase 8.2.8 production forecast producer, once certified
- MTG export producer, once reconciled to the Phase 8.2.8 output contract

## Non-authoritative but retained pathways

Historical scenario builders, one-time installers, hotfixes, prior closeout scripts, and dated certification artifacts remain referenceable but must not be called by the production entry point unless explicitly reinstated and recertified.

## Required production outputs

The final pipeline must produce, at minimum:

- Collector universe reconciliation
- Current-price quality review
- Historical-quality review
- Evidence and signal review
- Method-routing reconciliation
- Comparable contribution review
- Forecast results at one, three, and five years
- Downside, base, and upside scenarios
- Forecast reasonableness diagnostics
- Extreme-value and manual-review queues
- Purchase analysis
- Deferred-product report
- MTG-to-UIP reconciliation
- Owner acceptance summary

## Certification rule

Passing automated tests is necessary but insufficient. Final certification requires:

- Structural reconciliation
- Data-quality review
- Economic and semantic review
- Output acceptance
- Dynamic UIP reconciliation
- Explicit owner approval

## Change-control rule

No material change to product admission, pricing hierarchy, history treatment, evidence sources, method routing, comparable policy, forecasting formulas, thresholds, weights, uncertainty, recommendations, export semantics, or UIP mapping is certified without a version change, recertification, and explicit owner approval.
