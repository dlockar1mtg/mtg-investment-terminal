# Collector Candidate Methodology v2

## Status

Approved for development and testing only. Not authorized for production forecasts, purchase recommendations, automatic model updates, reverse-score production use, or the Japanese FINAL FANTASY hybrid formula.

## Owner decisions recorded

- COL-METH-001: APPROVE_DIAGNOSTIC_ONLY
- COL-METH-002: APPROVE_SIMPLE_RETURN_UNTIL_365_DAYS
- COL-METH-003: APPROVE_TRIMMED_MEAN_10_PERCENT
- COL-METH-004: APPROVE_DISCLOSURE_AND_REVIEW
- COL-METH-005: APPROVE_DISCLOSE_REVIEW_NO_AUTOMATIC_CAP
- COL-METH-006: APPROVE_PRIMARY_COMPARABLE_KEEP_FORMULA_INACTIVE

## Candidate v2 behavior

- Comparable products use a 10% trimmed peer mean plus the separately traced fundamental adjustment.
- Limited-history products use simple observed return until 365 days, blended with the trimmed peer mean under the existing 25% history / 75% comparable route weights.
- Reversed pair scores remain diagnostic only and cannot become production inputs through this approval.
- Dominant-peer sensitivity is disclosed and review-gated rather than automatically excluded.
- Extreme annual rates are disclosed and review-gated rather than automatically clipped.
- Japanese FINAL FANTASY keeps its owner-approved primary comparable, but the hybrid formula remains inactive.

## Outputs

`data/operations/collector_candidate_methodology_v2/candidate_v2_0_0/`

- `collector_candidate_methodology_v2_forecasts.csv`
- `collector_candidate_methodology_v2_comparison.csv`
- `collector_candidate_methodology_v2_route_summary.csv`
- `collector_candidate_methodology_v2_owner_approval_register.csv`
- `collector_candidate_methodology_v2_summary.json`

## Commands

```powershell
python scripts\build_collector_candidate_methodology_v2.py
python scripts\build_collector_candidate_methodology_v2.py --strict
python scripts\audit_collector_candidate_methodology_v2.py
python scripts\audit_collector_candidate_methodology_v2.py --strict
```

## Required boundaries

- Candidate development authorized: true
- Candidate testing authorized: true
- Candidate projection authorized: false
- Production projection authorized: false
- Purchase recommendation authorized: false
- Automatic model update allowed: false
- Japanese hybrid formula authorized: false
