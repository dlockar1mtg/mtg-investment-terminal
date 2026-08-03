# Collector Candidate Methodology v2.2

## Purpose

Implement the owner-approved COL-METH-003 amendment for development and testing only.

## Approved amendment

- Remove the highest and lowest 10 percent of peer returns.
- Apply target-specific similarity weights to the remaining peers.
- Preserve the separately documented fundamental adjustment.
- For limited-history products, use the governed simple historical return and apply the route blend exactly once.

## Preserved controls

- Reverse-score routes remain diagnostic only.
- Japanese FINAL FANTASY remains formula-inactive.
- No candidate projection, production forecast, purchase recommendation, or automatic model update is authorized.

## Required outputs

- `collector_candidate_methodology_v2_2_forecasts.csv`
- `collector_candidate_methodology_v2_2_peer_lineage.csv`
- `collector_candidate_methodology_v2_2_comparison.csv`
- `collector_candidate_methodology_v2_2_route_summary.csv`
- `collector_candidate_methodology_v2_2_owner_approval_register.csv`
- `collector_candidate_methodology_v2_2_summary.json`

## Acceptance targets

- 51 products total.
- 50 complete candidate calculations.
- One inactive Japanese hybrid.
- Seven reverse-score diagnostic-only products.
- 31 peer-lineage targets.
- More than one comparable-route weighted-trimmed value.
- Seven distinct limited-route weighted-trimmed values.
- Six owner decisions represented.
- All activation and production boundaries closed.
