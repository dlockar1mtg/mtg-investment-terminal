# v13.2 Changelog

## Fixed
- Added required identifiable User-Agent headers to TCGCSV archive downloader.
- Replaced deprecated `pd.Timestamp.utcnow()` with `pd.Timestamp.now('UTC')`.
- Improved 401 error message with practical browser/manual-cache fallback.

## Updated
- `backfill_tcgcsv_monthly_history.py`
