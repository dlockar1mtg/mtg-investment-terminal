# Phase 11E.12 — Current-Market Quality and Accumulation

This milestone converts completed eBay production attempts into a persistent,
quality-gated current asking-price history.

It does not label eBay Browse listings as sold-price history.

## Outputs

- `latest_listing_quality_review.csv`
- `latest_current_market_snapshot.csv`
- `universal_mtg_current_asking_history.csv`
- `current_market_manual_review_queue.csv`
- `current_market_accumulation_summary.json`

## One-cycle command

```powershell
python .\scripts\run_phase_11e_12_accumulation_cycle.py
```

The cycle consumes the latest successful production attempt, applies identity
quality gates, builds one product-date snapshot from automatically approved
listings, appends it using a deterministic fingerprint, and rebuilds the
governed historical ledger.
