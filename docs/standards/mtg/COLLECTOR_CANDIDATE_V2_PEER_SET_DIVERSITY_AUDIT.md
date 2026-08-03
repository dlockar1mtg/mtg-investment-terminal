# Collector Candidate v2 Peer-Set Diversity Audit

## Purpose

Candidate Methodology v2 produced the same 10% trimmed peer mean for all 24 comparable-adjusted products. This batch determines whether that result is caused by valid target-specific peer sets, repeated peer-return sets, or an unintended shared global pool.

## Controls

- Fingerprint every target's peer IDs.
- Fingerprint every target's peer-return multiset.
- Recompute the 10% trimmed mean directly from target rows.
- Compare recomputed values with Candidate v2 stored values.
- Fail strict mode if all 31 comparable-driven targets share one peer set.
- Preserve all forecast and purchase authorization boundaries as false.

## Outputs

- `collector_candidate_v2_peer_set_detail.csv`
- `collector_candidate_v2_peer_set_groups.csv`
- `collector_candidate_v2_peer_set_audit_summary.json`

## Interpretation

A PASS means stored trimmed means are traceable to target-specific peer rows and at least two distinct peer sets exist. A FAIL requires repairing peer selection or aggregation before Candidate v2 can advance.
