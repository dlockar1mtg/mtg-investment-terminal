# Collector Leakage-Safe Walk-Forward Replay Foundation

## Purpose

Suspend the Candidate v2.3 technical freeze and establish a historically valid replay boundary before measuring forecast or decision accuracy.

## Governing principle

At each historical decision cutoff, the replay may use only records whose knowledge date is on or before that cutoff. Future realized prices are held out and used only as outcomes.

Today's Candidate v2.3 outputs are prohibited as historical inputs. The replay must reconstruct every route component from point-in-time evidence.

## Phase 1 outputs

- source inventory with column lineage and SHA-256 hashes
- month-end historical decision schedule
- product-by-cutoff eligibility matrix
- held-out outcome availability at 90, 180, and 365 days
- foundation summary and strict audit

## What Phase 1 does not do

- It does not generate historical forecasts.
- It does not score model accuracy.
- It does not infer unavailable historical features.
- It does not certify prospective performance.
- It does not authorize production forecasts or purchases.

## Required next phase

After the foundation passes, build the point-in-time replay engine. For every cutoff and eligible product, it must reconstruct the applicable Candidate v2.3 route using only then-available observations, comparables, fundamental fields, route rules, scenario rules, and confidence rules.

The replay engine must preserve the exact model version while allowing the evidence set to grow naturally through time.

## Accuracy outputs required later

- forecast annual rate and projected price at each cutoff
- decision state based on a separately governed historical decision rubric
- realized 90-, 180-, and 365-day return
- absolute and signed forecast error
- direction accuracy
- downside/base/upside interval coverage
- calibration by confidence band
- metrics by route, history depth, release cohort, and forecast horizon
- benchmark comparison against no-change, route median, and simple trailing-return baselines
- parameter-change recommendations kept inactive pending owner approval

## Freeze status

Candidate v2.3 remains an unfrozen development candidate until leakage-safe replay and accuracy evaluation are completed and reviewed.
