# Phase 10.19 — eBay Production Rollout Certification

## Status

**PASS**

Phase 10.19 certifies bounded production use of the governed `precision-v2`
eBay matcher for Collector Booster Display collection.

## Repository Controls

- Branch: `phase-10.19-ebay-production-rollout`
- Production matcher: `precision-v2`
- Matcher entry point:
  `terminal2.market_sources.ebay_precision_v2.identity_match_listing`
- Product selection: deterministic targeted product map
- Purchasing: disabled
- Credential output: prohibited
- Matcher fallback: fail closed

## Automated Certification

- Focused tests: 137 passed
- Bounded rollout map tests: PASS
- Production adapter tests: PASS
- Product identity tests: PASS
- Offline replay tests: PASS
- Fail-closed validator tests: PASS

## Five-Product Canary

- Products requested: 5
- Products processed: 5
- Listings returned: 25
- Accepted: 11
- Review: 0
- Rejected: 14
- Queries used: 10
- Aborted early: false
- Missing requested products: 0
- Credentials printed: false
- Status: PASS

## Bounded 25-Product Rollout

- Run ID: `EBAY20260727T105316Z`
- Selection mode: `PRODUCT_MAP_TARGETED`
- Products requested: 25
- Products processed: 25
- Listings returned: 125
- Maximum permitted listings: 125
- Queries used: 50
- Accepted: 69
- Review: 1
- Rejected: 55
- Missing requested products: 0
- Aborted early: false
- Credentials printed: false
- Matcher version: `precision-v2`
- Matcher fail closed: true
- Validator errors: 0
- Status: PASS

### Coverage States

- Strong match coverage: 2
- Limited match coverage: 22
- Ambiguous results: 1

## Governed Japanese-Language Variant Correction

The bounded rollout identified a reversed language policy for:

`FINAL FANTASY - Collector Booster Display (Japanese)`

The policy was corrected and certified as follows:

- Japanese target + Japanese collector box: eligible for normal matching
- Japanese target + explicit English collector box: REJECTED
- Japanese target + no language marker: REVIEW
- Japanese target + wrong product form: REJECTED
- Default/English target + Japanese listing: existing rejection policy retained

### Saved-Evidence Replay

- Saved listing rows: 125
- Products represented: 25
- API quota calls: 0
- Classification changes: 1
- Evidence changes: 5
- Upgrade transitions: 0
- Before: 69 ACCEPTED, 55 REJECTED, 1 REVIEW
- After governed replay: 69 ACCEPTED, 56 REJECTED
- Transition: the explicit English listing moved from REVIEW to REJECTED

### Exact Language Checks

- Japanese Collector Booster Box: ACCEPTED, score 1.0
- English Collector Booster Box: REJECTED, language-variant conflict
- Japanese Value Booster: REJECTED, wrong product form

## Operational Decision

Phase 10.19 is certified for bounded production eBay collection using
`precision-v2`.

The next live expansion must:

- use the second deterministic 25-product half of the certified 50-product map;
- keep `--limit-per-product 5`;
- enforce a 125-row maximum;
- stop on source error, early abort, missing product, matcher fallback,
  credential output, or row-limit violation;
- avoid repeating the first 25-product batch unless investigating a specific
  regression.
