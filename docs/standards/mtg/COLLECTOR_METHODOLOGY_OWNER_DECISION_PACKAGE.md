# Collector Methodology Owner Decision Package

## Purpose

Convert the completed Collector methodology sensitivity evidence into a concise, nonbinding owner-review package without changing the 51-product diagnostic baseline.

## Inputs

- Collector methodology sensitivity review
- Collector methodology evidence review
- Collector route reconciliation output

## Outputs

- Product-level nonbinding recommendations
- Route-level nonbinding recommendations
- Six-topic owner decision register
- Recommended inactive candidate methodology JSON
- Package summary

## Recommendation boundaries

The package may recommend a next candidate treatment, but it does not approve or activate:

- symmetric comparable-score reuse
- short-history annualization rules
- peer aggregation rules
- dominant-peer exclusions
- extreme-rate clipping or acceptance
- Japanese FINAL FANTASY hybrid formula
- candidate or production forecasts
- purchase recommendations
- automatic model updates

## Proposed candidate direction for owner review

- Use a 10% trimmed peer mean as the next comparable aggregation candidate.
- Use simple observed return until at least 365 observed days are available.
- Keep reversed comparable scores diagnostic only pending prospective validation.
- Disclose dominant-peer concentration and require review rather than silently excluding peers.
- Disclose extreme annual rates and require review rather than automatically clipping them.
- Preserve the owner-approved Japanese FINAL FANTASY primary comparable while keeping the hybrid formula inactive.

## Required execution

```powershell
python scripts\build_collector_methodology_owner_decision_package.py
python scripts\build_collector_methodology_owner_decision_package.py --strict
python scripts\audit_collector_methodology_owner_decision_package.py
python scripts\audit_collector_methodology_owner_decision_package.py --strict
```

A passing audit validates package completeness and authorization boundaries only. It is not methodology approval or production certification.
