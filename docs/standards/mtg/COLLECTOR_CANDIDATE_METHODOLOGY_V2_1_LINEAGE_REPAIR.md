# Collector Candidate Methodology v2.1 Lineage Repair

## Purpose

Repair Candidate v2 component lineage after the peer-set audit found that the sensitivity output named `variant_peer_trimmed_mean_10_percent` contained a full route-level variant rather than a peer-only component. Candidate v2 incorrectly reused that route-level result as a peer input and blended the seven limited-history products a second time.

## v2.1 rules

- Recompute the 10% trimmed peer mean directly from `collector_reconciled_peer_contributions.csv` for each target.
- Read limited-history simple returns from the governed retrospective outcome diagnostics.
- Apply the route blend exactly once.
- Preserve the owner-approved unweighted 10% trimmed mean as the v2.1 candidate calculation.
- Calculate a similarity-weighted trimmed mean only as an inactive amendment diagnostic.
- Keep reverse-score routes diagnostic-only.
- Keep the Japanese FINAL FANTASY hybrid formula inactive.
- Keep candidate projection, production projection, purchase recommendation, and automatic update authorization false.

## Important methodology finding

The 24 comparable-adjusted targets share one identical 26-peer return set, and the seven limited-history targets share one identical 21-peer return set. An unweighted trimmed mean therefore produces one common peer component within each route group. Target-specific similarity scores only affect the separate similarity-weighted trimmed diagnostic.

This batch does not approve a change from unweighted to similarity-weighted trimming. It creates the evidence needed for a separate owner amendment decision.

## Expected result

- 51 products
- 50 complete v2.1 candidate calculations
- one intentionally inactive Japanese hybrid
- seven reverse-score diagnostic-only products
- 31 peer-lineage rows
- one-time route blending for every applicable product
- no production or purchase authorization
