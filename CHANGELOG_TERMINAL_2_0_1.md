# MTG Investment Terminal 2.0.1 Changelog

## Fixed
- `sqlite3.ProgrammingError: Error binding parameter 1: type 'Series' is not supported`
- Rewrote the score insert query to use explicit scalar extraction.
- Removed ambiguous duplicate-column query behavior in `terminal2/analytics/scoring.py`.

## Updated
- `terminal2/analytics/scoring.py`
