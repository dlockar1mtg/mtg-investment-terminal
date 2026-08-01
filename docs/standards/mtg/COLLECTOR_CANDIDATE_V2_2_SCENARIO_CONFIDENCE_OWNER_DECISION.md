# Collector Candidate v2.2 Scenario and Confidence Owner Decision Package

## Purpose

This package converts the completed scenario-and-confidence diagnostic review into two explicit owner decisions. It does not activate either recommendation.

## Decisions

### COL-SCEN-001 — Scenario width methodology

Nonbinding recommendation: `APPROVE_ROUTE_BOUNDED_EVIDENCE_WIDTH_WITH_95_PERCENT_LOSS_FLOOR`.

The proposed width is the maximum of the route minimum, available retrospective volatility, and half the methodology sensitivity spread. It is bounded by a route maximum and by an annual downside floor of -95%.

Proposed route bounds:

- Calibrated history: 0.10 to 0.20
- Comparable adjusted: 0.20 to 0.45
- Limited history: 0.30 to 0.75
- Japanese hybrid: 0.35 to 0.60, but the formula remains inactive

### COL-CONF-001 — Confidence methodology

Nonbinding recommendation: `APPROVE_NORMALIZED_EVIDENCE_CONFIDENCE_0_TO_100`.

The internal calculation uses a 0-to-1 scale and exports a 0-to-100 score. Factors include route maturity, peer depth, methodology sensitivity, retrospective volatility, short-history status, reverse-score status, and concentration.

Reverse-score products have a proposed confidence ceiling of 10. The inactive Japanese formula has a proposed ceiling of 15.

## Authorization boundaries

The decision package does not authorize:

- Scenario methodology activation
- Confidence methodology activation
- Candidate projections
- Production projections
- Purchase recommendations
- Automatic model updates

## Run commands

```powershell
python scripts\build_collector_candidate_v2_2_scenario_confidence_owner_decision.py
python scripts\build_collector_candidate_v2_2_scenario_confidence_owner_decision.py --strict
python scripts\audit_collector_candidate_v2_2_scenario_confidence_owner_decision.py
python scripts\audit_collector_candidate_v2_2_scenario_confidence_owner_decision.py --strict
```
