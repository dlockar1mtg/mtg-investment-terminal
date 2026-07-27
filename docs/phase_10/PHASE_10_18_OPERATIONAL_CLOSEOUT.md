# Phase 10.18 Operational Closeout

## Repository State

- Merge commit: `79802e0`
- Certification tag: `mtg-phase-10.18-certified`
- Production matcher: `precision-v2`
- Matcher entry point:
  `terminal2.market_sources.ebay_precision_v2.identity_match_listing`

## Offline Certification

- Focused tests: 123 passed
- Saved listings replayed: 1,330
- Unique products replayed: 147
- Upgrade transitions: 0
- eBay quota calls during replay: 0
- Booster pack-count false downgrades: 0

## Live Canary

- Run ID: `EBAY20260727T104513Z`
- Selection mode: `PRODUCT_MAP_TARGETED`
- Products requested: 5
- Products processed: 5
- Missing products: 0
- Listings returned: 25
- Accepted: 11
- Review: 0
- Rejected: 14
- Queries used: 10
- Aborted early: false
- Credential output: false
- Matcher fail closed: true
- Status: PASS

## Product Coverage

| Product | Accepted | Listings | Coverage |
|---|---:|---:|---|
| Adventures in the Forgotten Realms Collector Booster Display | 1 | 5 | LIMITED_MATCH_COVERAGE |
| Aetherdrift Collector Booster Display | 4 | 5 | LIMITED_MATCH_COVERAGE |
| Avatar: The Last Airbender Collector Booster Display | 3 | 5 | LIMITED_MATCH_COVERAGE |
| Bloomburrow Collector Booster Display | 1 | 5 | LIMITED_MATCH_COVERAGE |
| Commander Legends Collector Booster Display | 2 | 5 | LIMITED_MATCH_COVERAGE |

## Scope Limitation

The certified source map contained Collector Booster Displays. This canary
therefore certifies the live Collector Booster Display path. Secret Lair and
other booster-display product forms remain certified through offline replay and
tests but were not represented in this live five-product sample.

## Decision

Phase 10.18 is production certified for governed precision-v2 eBay collection.

The next production expansion must remain bounded and must stop on:

- nonzero process exit;
- rate-limit or source error;
- early abort;
- missing requested products;
- matcher version other than `precision-v2`;
- fail-closed metadata missing;
- credentials printed;
- listing count exceeding the configured maximum.
