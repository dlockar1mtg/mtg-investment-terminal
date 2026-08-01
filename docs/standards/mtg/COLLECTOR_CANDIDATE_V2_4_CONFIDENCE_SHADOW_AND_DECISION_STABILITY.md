# Collector Candidate v2.4 Confidence Shadow and Decision Stability

## Approved confidence scope

- Horizons: 90 and 180 days only.
- Method: `PRIOR_PRODUCT_MAE_PLUS_FORECAST_EXTREMENESS`.
- Structure: `STANDARD_CONFIDENCE` and `LOW_CONFIDENCE`.
- Low-confidence rule: bottom prospective-reliability tercile.
- No separate high/medium confidence distinction.
- No 365-day confidence authorization.

## Decision-state scope

Decision states remain unauthorized. The batch evaluates cutoff-level stability for four leading 90-day threshold pairs: 40/60, 40/75, 33/75, and 25/75 percentiles. A configuration is only marked owner-review eligible when ordinal realized-return ordering passes at least 60% of eligible cutoffs.

## Governance boundaries

This batch does not authorize Candidate v2.4 promotion, production projections, purchase recommendations, automatic model updates, technical freeze, or UIP acceptance. Freeze remains suspended pending full Collector route reconstruction and replay.
