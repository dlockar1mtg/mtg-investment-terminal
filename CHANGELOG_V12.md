# v12 Changelog

## Added
- Persistent daily market observations database.
- Rolling price metrics.
- Real-signal scoring engine.
- Optional input templates for inventory, sales velocity, demand, and scarcity.
- `review_real_signals.py`.

## Changed
- Workflow now appends market observations before scoring.
- Scoring includes `real_signal_score` at a conservative 12% weight.

## Notes
- The system improves as daily observations accumulate and as optional market input CSVs are populated.
