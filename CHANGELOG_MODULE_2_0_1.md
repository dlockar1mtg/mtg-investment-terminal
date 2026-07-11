# Module 2.0.1 Hotfix

## Fixed

- `AttributeError: 'numpy.float64' object has no attribute 'notna'`
- Missing market-health columns now produce index-aligned pandas Series.
- Current price safely falls back to `latest_price`.
- Products-updated-today calculation now handles absent or incomplete columns.

## Updated file

```text
terminal2/market/analytics/health.py
```
