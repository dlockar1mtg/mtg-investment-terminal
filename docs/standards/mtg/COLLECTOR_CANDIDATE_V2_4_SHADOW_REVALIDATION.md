# Collector Candidate v2.4 Shadow Implementation and Revalidation

## Approved scope

Owner approval authorizes shadow implementation only:

- Retain the current 90-day point forecast.
- Add a 90-day 68% symmetric conformal interval using expanding matured history and 50% median-bias shrinkage.
- Use a 180-day point forecast composed of 75% product momentum and 25% cutoff-level Collector median momentum, calibrated from the last two matured cutoffs, with no bias correction.
- Retain the current 365-day methodology.

The approval does not authorize production forecasts, purchase recommendations, automatic model updates, technical freeze, or UIP acceptance.

## Consolidated batch

Run:

```powershell
python scripts\build_collector_candidate_v2_4_shadow_revalidation.py
python scripts\build_collector_candidate_v2_4_shadow_revalidation.py --strict
python scripts\audit_collector_candidate_v2_4_shadow_revalidation.py
python scripts\audit_collector_candidate_v2_4_shadow_revalidation.py --strict
```

Outputs are written to:

`data/operations/collector_candidate_v2_4_shadow_revalidation/candidate_v2_4_0_shadow`

The batch produces historical shadow predictions, horizon comparisons, 90-day interval coverage, confidence-bucket diagnostics, decision-state diagnostics, and a governance summary. It does not overwrite Candidate v2.3 or authorize Candidate v2.4 for production.
