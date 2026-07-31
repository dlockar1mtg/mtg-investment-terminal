# Collector Dual-Track Evaluation Consolidated Batch

## Purpose

This batch corrects the lane-scope expansion discovered during deep-history recovery and establishes two distinct evidence tracks:

1. **Retrospective outcome track** — recovered historical prices may support outcome and pattern analysis, but remain prohibited as historical decision inputs while knowledge availability is unproven.
2. **Prospective decision track** — current information is captured with an explicit decision date, model version, route reference, current price, evidence fields, and missing-input flags so it can mature into leakage-free walk-forward evidence.

## Scope correction

The recovery output containing 191 products mixed Collector, Pre-Collector, and other booster products. This batch rebuilds the universe from Collector-specific governed sources and excludes Secret Lair and non-Collector products from the active lane output.

The product count remains dynamic. No fixed expectation of 49, 50, or 51 products is encoded.

## Retrospective track

Retrospective observations must satisfy:

- normalized governed Collector identity;
- valid observation date;
- positive price;
- observation date on or after governed release date;
- preserved source lineage;
- deterministic deduplication.

Every retrospective row remains:

- `historical_decision_input_eligible = false`;
- `knowledge_availability_status = RETROSPECTIVE_AVAILABILITY_UNPROVEN`.

Eligible retrospective rows may be used for outcome measurement and historical-pattern diagnostics only.

## Prospective track

The prospective snapshot records the information available when the script runs, including:

- snapshot identifier;
- decision date and capture timestamp;
- product identity and release date;
- future-release and current-investment eligibility;
- current price and price date;
- current route reference;
- candidate model version;
- evidence and historical-return fields where available;
- missing-price, missing-route, and missing-release flags;
- explicit projection and purchase authorization states.

The snapshot is a data-capture artifact, not a forecast authorization.

## Governance boundaries

The batch does not:

- authorize retrospective prices as historical decision inputs;
- authorize the historical snapshot builder for backdated simulations;
- activate candidate or production projections;
- authorize purchase recommendations;
- permit automatic model updates.

## Required execution

```powershell
python scripts\build_collector_dual_track_evaluation_candidate.py
python scripts\build_collector_dual_track_evaluation_candidate.py --strict
python scripts\audit_collector_dual_track_evaluation_candidate.py
python scripts\audit_collector_dual_track_evaluation_candidate.py --strict
```

## Next milestone

After this batch passes, the next consolidated build may add:

- diagnostic candidate forecast calculations under the inactive numeric specification;
- historical outcome matching for retrospective research;
- append-safe prospective snapshot history;
- future matured-outcome evaluation;
- route and comparable reconstruction using information captured at each prospective decision date.
