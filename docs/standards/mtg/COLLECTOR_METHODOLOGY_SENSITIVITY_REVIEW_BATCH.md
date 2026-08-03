# Collector Methodology Sensitivity Review

## Purpose

This inactive diagnostic batch compares alternative calculation treatments without changing the reconciled 51-product baseline.

## Inputs

- Reconciled 51-product candidate forecasts
- Reconciled peer contributions
- Methodology evidence product review
- Retrospective outcome diagnostics

## Diagnostic variants

- Baseline similarity-weighted peer mean
- Median peer return
- 10% trimmed peer mean
- Top-five similarity-weighted peers
- Dominant-peer exclusion
- Short-history simple return
- Short-history annualized return

## Outputs

- `collector_methodology_sensitivity_product_review.csv`
- `collector_methodology_sensitivity_variants.csv`
- `collector_methodology_sensitivity_route_summary.csv`
- `collector_methodology_sensitivity_owner_decisions.csv`
- `collector_methodology_sensitivity_review_summary.json`

## Interpretation boundary

The variants are diagnostic comparisons. They do not replace the baseline, certify forecast accuracy, approve symmetric comparable reuse, activate parameters, authorize forecasts, or authorize purchases.

## Required owner decisions

1. Symmetric comparable-score reuse
2. Short-history annualization
3. Peer aggregation method
4. Dominant-peer treatment
5. Extreme annual-rate treatment
6. Japanese FINAL FANTASY hybrid numeric methodology

## Execution

```powershell
python scripts\build_collector_methodology_sensitivity_review.py
python scripts\build_collector_methodology_sensitivity_review.py --strict
python scripts\audit_collector_methodology_sensitivity_review.py
python scripts\audit_collector_methodology_sensitivity_review.py --strict
```
