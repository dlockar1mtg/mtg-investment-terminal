# Collector Methodology Decision Capture

## Purpose

This inactive batch records the six pending Collector methodology decisions and reconciles the difference between the complete baseline annual rate and the peer-only weighted sensitivity rate for comparable products.

## Boundaries

- The difference is labeled `unresolved_non_peer_adjustment`.
- No unsupported economic meaning is assigned to that difference.
- The difference remains unauthorized until its source is documented.
- All six owner decisions remain pending unless explicitly approved by the owner.
- No candidate, production, purchase, or automatic-update authorization is granted.

## Outputs

- `collector_comparable_baseline_adjustment_reconciliation.csv`
- `collector_comparable_adjustment_groups.csv`
- `collector_methodology_owner_decision_ballot.csv`
- `collector_methodology_decision_capture_specification.json`
- `collector_methodology_decision_capture_summary.json`

## Required owner decisions

1. Symmetric comparable-score reuse
2. Short-history annualization
3. Peer aggregation method
4. Dominant-peer treatment
5. Extreme annual-rate treatment
6. Japanese FINAL FANTASY hybrid numeric methodology

## Activation gate

No methodology may be activated until all six decisions are recorded and the baseline adjustment source is reconciled and documented.
