# Collector Numeric Specification Candidate Review

## Purpose

This document explains the first exact numeric candidate derived from the owner-approved Collector methodology concepts. The candidate is for diagnostics and backtesting only.

It is not an approved production method. It does not authorize forecasts or purchases.

## Approved conceptual boundaries

- Mature direct-history products may use a robust blend of governed historical return windows.
- Historical maturity is not a universal eligibility gate.
- Limited-history products use minority direct history and majority comparable evidence.
- Comparable products are weighted using governed similarity evidence.
- Hybrid products use comparable-majority evidence with a minority fundamental contribution.
- Scenarios and confidence are evidence-derived.
- Supply, demand, liquidity, and reprint adjustments are bounded and separately disclosed.
- Daily refresh is the intended operating state.
- No hard forecast caps or silent clipping are permitted.
- Purchase calculations may be developed, but recommendations remain unauthorized.

## Candidate values for testing

### Direct-history calibrated

The candidate blends 90-day, 180-day, and 365-day governed annualized returns with weights of 20%, 30%, and 50%. Missing approved windows are omitted and the remaining weights are renormalized.

This candidate applies only to products already routed to `DIRECT_HISTORY_CALIBRATED`.

### Direct-history limited

The candidate uses 25% governed product history and 75% similarity-weighted comparable evidence.

This is intended to preserve early product-specific information without allowing a short series to dominate.

### Comparable-product adjusted

Each selected peer receives a normalized weight based on `adjusted_similarity_score`. Every peer contribution remains visible.

### Fundamental-comparable hybrid

The candidate uses 75% approved comparable evidence and 25% fundamental evidence.

### Market-factor adjustment

The candidate translates score deviations from neutral into separately disclosed annual-rate adjustments. The total adjustment is bounded to plus or minus four annual percentage points for testing.

These values are proposals, not approvals.

### Confidence and scenarios

Candidate confidence uses evidence completeness, evidence agreement, history or peer quality, and method-specific support. Candidate classes are High at 75 or above, Moderate at 55 or above, and Low below 55.

Scenario width will be derived from historical or peer dispersion, evidence incompleteness, disagreement, and method limitations. No hard forecast cap is used.

## Intentionally unset values

The following values remain unset until actual diagnostics support them:

- Freshness warning threshold
- Freshness fail-closed threshold
- Extreme-forecast review threshold
- Purchase decision thresholds
- Recommendation labels

Daily refresh remains the target. Freshness diagnostics exist to detect failed refreshes or unavailable data, not to replace daily collection.

## Required next stage

1. Validate this candidate remains inactive.
2. Build a non-production calculation and diagnostic engine.
3. Run the candidate across the governed Collector universe.
4. Review early-release products, extreme outputs, peer concentration, and scenario widths.
5. Backtest wherever historical outcomes permit.
6. Present the observed results and proposed changes to the owner.
7. Record separate approval before activation.
