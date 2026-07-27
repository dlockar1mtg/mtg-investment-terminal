# Phase 10.21 — Full-Universe Replay and Production Migration

## Objective

Migrate the governed eBay collection pipeline from `precision-v2` to
`precision-v3-universal` using a canonical full-universe offline replay and one
bounded live production run.

## Repository Certification

- Focused Phase 10.21 tests: 42 passed
- Full repository suite: 534 passed
- Failures: 0
- Existing warnings: 13

## Canonical Evidence Replay

- Mode: `FULL_UNIVERSE_PRODUCTION_MIGRATION`
- Status: PASS
- Quota calls: 0
- Baseline matcher: `precision-v2`
- Migration matcher: `precision-v3-universal`
- Migration policy: `downgrade_only`
- Evidence canonicalization: enabled
- Deduplication key:
  - `canonical_product_id`
  - `ebay_item_id`
- Discovered source files: 30
- Included source files: 24
- Excluded source files: 6
- Raw listing rows: 11,306
- Canonical listing rows: 10,677
- Duplicate rows removed: 629
- Rows missing eBay item ID: 0
- Unique products: 1,050
- Saved-to-migrated upgrade transitions: 0
- Precision-v2-to-v3 upgrade transitions: 0

## Offline Migration Impact

### State Counts

| State | Saved | Precision v2 | Precision v3 | Migrated |
|---|---:|---:|---:|---:|
| Accepted | 3,010 | 2,414 | 1,827 | 1,793 |
| Review | 1,986 | 4,191 | 4,765 | 3,174 |
| Rejected | 5,681 | 4,072 | 4,085 | 5,710 |

### Precision-v2 to Precision-v3 Transitions

| Transition | Listings |
|---|---:|
| Accepted → Accepted | 1,827 |
| Accepted → Review | 581 |
| Accepted → Rejected | 6 |
| Review → Review | 4,184 |
| Review → Rejected | 7 |
| Rejected → Rejected | 4,072 |

The universal matcher produced no classification upgrades. All changes were
conservative downgrades or retained classifications.

## Bounded Live Production Migration

- Run ID: `EBAY20260727T125933Z`
- Status: PASS
- Live API called: true
- Selection mode: `PRODUCT_MAP_TARGETED`
- Products requested: 25
- Products processed: 25
- Missing products: 0
- Limit per product: 5
- Maximum listing rows: 125
- Listing rows returned: 125
- Queries used: 50
- Accepted rows: 62
- Review rows: 6
- Rejected rows: 57
- Strong match coverage products: 2
- Limited match coverage products: 23
- Aborted early: false
- Credentials printed: false
- Matcher fail closed: true
- Universal classification policy: true
- Universal policy mode: `downgrade_only`

## Live Validation

The bounded rollout validator returned:

- Status: PASS
- Mode: `BOUNDED_ROLLOUT_VALIDATION`
- Expected products: 25
- Maximum listing rows: 125
- Errors: none

## Production Decision

Phase 10.21 is certified for production migration to
`precision-v3-universal`.

The certification is supported by two independent proof layers:

1. A canonical offline replay of 10,677 unique saved listing observations
   across 1,050 products with zero unsafe upgrades.
2. A bounded live production run covering 25 products and 125 listings with no
   missing products, no early abort, no credential disclosure, and a clean
   fail-closed validator result.

## Safety Constraints Preserved

- Purchasing remains disabled.
- Allocation behavior was not modified.
- The matcher remains fail closed.
- Legacy matcher selection remains unavailable.
- The universal classification policy is downgrade only.
- Production collection remains bounded by explicit product and listing limits.
