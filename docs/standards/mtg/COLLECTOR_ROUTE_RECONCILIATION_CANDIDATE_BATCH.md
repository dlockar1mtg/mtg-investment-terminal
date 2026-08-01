# Collector Route Reconciliation Candidate

## Purpose

This batch repairs the full-route regression without recalculating the 43 products that already passed the comparable-repair baseline.

## Baseline preservation

The following repaired products are copied forward unchanged:

- 19 `DIRECT_HISTORY_CALIBRATED`
- 24 `COMPARABLE_PRODUCT_ADJUSTED`

The reconciliation logic operates only on the eight previously incomplete routes:

- seven `DIRECT_HISTORY_LIMITED`
- one `FUNDAMENTAL_COMPARABLE_HYBRID`

## Identity handling

Comparable edge identifiers may be stored as numeric TCGplayer IDs or canonical values such as `TCGCSV-24495-657852`. The reconciliation builder resolves either representation to the numeric TCGplayer ID before matching.

## Limited-history completion

For each limited-history product, the builder:

1. derives a retrospective annualized history component from governed outcome history;
2. searches for direct existing comparable edges;
3. when no direct edge exists, reverses existing explicit pair-score relationships where the limited product was the peer;
4. preserves the original similarity score without recalculation;
5. labels reversed edges `CANDIDATE_DIAGNOSTIC_REQUIRES_OWNER_APPROVAL`.

Symmetric use is not production-approved by this batch.

## Japanese FINAL FANTASY

The owner-approved regular FINAL FANTASY primary comparable is injected for the Japanese display. The existing 75% comparable / 25% fundamental candidate blend remains unchanged.

## Required controls

- all peer returns remain `RETROSPECTIVE_DIAGNOSTIC_ONLY`;
- no future information may be treated as a decision-time input;
- the 43-product repaired baseline must not regress;
- forecast authorization remains false;
- purchase authorization remains false;
- automatic model updating remains false.

## Expected structural result

The strict target is:

- 51 total Collector products;
- 43 preserved repaired baseline products;
- 8 filled incomplete routes;
- 51 complete inactive diagnostics;
- 7 limited-history products using candidate reverse-pair evidence;
- 1 Japanese FINAL FANTASY owner-approved override.

These are structural completion targets, not accuracy certification or investment authorization.
