# Collector Walk-Forward Replay Phase 2A

## Purpose

Phase 2A performs the first scored, leakage-safe historical replay for Collector Booster products. It uses only information available at each historical month-end cutoff and held-out later prices for outcomes.

## Scope

The scored universe is restricted to product names containing `Collector Booster Display`. Broader sealed-product records remain outside the scored Collector universe.

## Reconstructability rule

Phase 2A only generates a full forecast where the approved route can be reconstructed from dated evidence.

- At least 365 days of history: `DIRECT_HISTORY_CALIBRATED_REPLAYABLE`.
- Between 90 and 364 days: `DIRECT_HISTORY_LIMITED_RECONSTRUCTION_REQUIRED` and blocked from a full forecast until point-in-time similarity weights and fundamental adjustments are available.
- Below 90 days: `INSUFFICIENT_HISTORY`.

Current Candidate v2.3 rates and current route assignments are prohibited as historical inputs.

## Scoring

For reconstructable calibrated-history forecasts, Phase 2A produces 90-, 180-, and 365-day comparisons against held-out outcomes and reports:

- mean and median absolute return error;
- root mean squared error;
- mean signed error;
- direction accuracy;
- scenario coverage;
- comparison with a no-change benchmark.

## Decision states

Test-only historical states are `FAVORABLE`, `WATCH`, `NEUTRAL`, `AVOID`, and `INSUFFICIENT_EVIDENCE`. They are retrospective evaluation labels only and do not authorize purchases.

## Limitations

Phase 2A is not a full replay of Candidate v2.3. Comparable-adjusted and limited-history routes remain blocked unless their target-specific historical similarity weights and historical fundamental adjustments can be proven available at each cutoff.

## Authorization

The technical freeze remains suspended. Production forecasts, purchase recommendations, reverse-score production use, automatic model updates, and Japanese hybrid activation remain unauthorized.
