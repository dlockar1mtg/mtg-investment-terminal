# Phase 10 Secret Lair Production Closeout

## Production scope

The Secret Lair lane contains a governed 973-product identity registry, complete three-tier model evaluation, finish-aware owned-inventory matching, portfolio valuation, owned-product forecasts, guarded recommendations, and Universal Investment Platform exports.

## Evaluation tiers

- `FULL_MODEL`: governed observed valuation and normal recommendation safeguards.
- `PROVISIONAL_MODEL`: provisional valuation with reduced confidence and watch-only recommendations.
- `STRUCTURAL_ONLY`: comparable-based structural estimate with data-needed recommendations.

## Standard production refresh

Run `scripts/run_secret_lair_production_refresh.py` with the current admission ledger and the local owned-inventory CSV. The command rebuilds the full evaluation and owned portfolio in one deterministic operation and writes a combined refresh manifest.

Then run `scripts/certify_phase_10_secret_lair_closeout.py` against that refresh manifest. Production closeout requires exact reconciliation to 973 products, the 214/380/379 tier split, zero unmatched holdings, complete output publication, and zero API quota calls.

## Data governance

Personal holdings and acquisition costs remain local. Generated validation, portfolio, forecast, recommendation, and certification outputs are reproducible artifacts and are not committed.

## Change-control rule

After certification, the Secret Lair lane is considered production-closed. Reopening development requires one of:

1. A reproducible defect or regression.
2. A source-contract or marketplace change.
3. An approved new capability with a separate milestone.
4. A governed model-policy revision.

Routine price refreshes and holdings updates do not reopen the lane.
