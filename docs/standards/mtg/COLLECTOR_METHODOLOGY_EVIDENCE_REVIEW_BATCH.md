# Collector Methodology Evidence Review Batch

## Purpose

This batch converts the complete 51-product inactive route baseline into an evidence-review package. It does not certify forecast accuracy and does not authorize projections or purchases.

## Inputs

- Reconciled 51-product candidate forecasts
- Reconciled peer contributions
- Reconciled completion edges
- Collector retrospective outcome history
- Current prospective decision snapshot

## Outputs

- `collector_methodology_product_review.csv`
- `collector_peer_concentration_diagnostics.csv`
- `collector_retrospective_outcome_diagnostics.csv`
- `collector_route_risk_summary.csv`
- `collector_owner_methodology_decisions.csv`
- `collector_methodology_evidence_review_summary.json`
- Append-safe prospective decision snapshot ledger

## Review topics

- Symmetric reuse of existing pair scores for seven limited-history products
- Short-history annualization risk
- Absolute base annual rates at or above 100%
- Peer concentration and effective peer counts
- Japanese FINAL FANTASY primary comparable override
- Retrospective drawdown and volatility evidence

## Authorization boundary

The following remain false:

- Candidate projection authorization
- Production projection authorization
- Purchase recommendation authorization
- Automatic model update permission

Retrospective evidence remains diagnostic only. Genuine walk-forward accuracy requires matured prospective snapshots.
