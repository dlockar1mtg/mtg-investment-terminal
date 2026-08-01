# Collector Candidate v2.2 Economic Reasonableness Review

## Purpose

Evaluate Candidate Methodology v2.2 rates, scenario direction, projected price magnitudes, and review thresholds before any candidate freeze or production-forecast decision.

## Scope

The batch reviews all 51 Collector products and expects 50 complete Candidate v2.2 calculations plus one intentionally inactive Japanese FINAL FANTASY hybrid.

## Review outputs

- Product-level economic review
- Route-level economic summary
- Flagged review queue
- Machine-readable review summary

## Diagnostic thresholds

- High absolute annual rate: 75%
- Extreme absolute annual rate: 100%
- Negative downside rate: below 0%
- Five-year price multiple: above 20x
- Low confidence review: below 0.50 when a confidence value exists

These are review thresholds only. They do not clip rates, approve forecasts, or establish purchase rules.

## Authorization boundaries

The batch does not authorize candidate projections, production projections, purchases, automatic updates, reverse-score production use, or the Japanese hybrid formula.

## Required commands

```powershell
python scripts\build_collector_candidate_v2_2_economic_review.py
python scripts\build_collector_candidate_v2_2_economic_review.py --strict
python scripts\audit_collector_candidate_v2_2_economic_review.py
python scripts\audit_collector_candidate_v2_2_economic_review.py --strict
```
