# v8.1 Changelog

## Fixed
- Replaced the old pandas-breaking target-buy line:
  `fair = df["fair_value_estimate"].astype(float).replace(0, current)`
- v8.1 includes the corrected `models/scoring.py` directly in the package.
