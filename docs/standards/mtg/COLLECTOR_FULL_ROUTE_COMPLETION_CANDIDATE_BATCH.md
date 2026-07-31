# Collector Full-Route Completion Candidate Batch

## Purpose

Complete inactive diagnostic calculations for the seven `DIRECT_HISTORY_LIMITED` products and the Japanese FINAL FANTASY `FUNDAMENTAL_COMPARABLE_HYBRID` product without activating forecasts, purchases, or automatic model updates.

## Inputs

- Repaired 51-product Collector candidate forecast output
- Governed retrospective Collector outcome history
- Existing normalized comparable pair scores
- Existing inactive numeric specification
- Owner-approved Japanese FINAL FANTASY primary comparable override

## Limited-history treatment

The history component is recomputed from the product's own governed retrospective price series when precomputed 90-, 180-, and 365-day fields are unavailable. This remains retrospective diagnostic evidence and is not represented as historically available decision input.

When a limited-history product has no direct target comparable rows, the batch creates a candidate diagnostic by reversing an already existing explicit pair score in which that product appears as the peer. No score is invented. However, symmetric reuse of a directional pair score is not owner-approved and is therefore disclosed as `CANDIDATE_DIAGNOSTIC_REQUIRES_OWNER_APPROVAL`.

## Japanese FINAL FANTASY treatment

The hybrid route injects the owner-approved primary comparable between the Japanese FINAL FANTASY display and the regular FINAL FANTASY display. The route remains inactive and uses the existing candidate 75% comparable / 25% fundamental blend.

## Outputs

- `collector_full_route_candidate_forecasts.csv`
- `collector_full_route_peer_contributions.csv`
- `collector_full_route_comparable_edges.csv`
- `collector_full_route_summary_by_route.csv`
- `collector_full_route_owner_review.csv`
- `collector_full_route_completion_summary.json`

## Authorization boundary

All scenario outputs remain diagnostics only. Candidate projection authorization, production projection authorization, purchase recommendation authorization, and automatic model updates remain false.

## Owner decision created by this batch

Approve or reject symmetric diagnostic reuse of existing explicit pair scores for limited-history products. Rejection does not invalidate the governed history component or the Japanese owner-approved override; it means direct limited-product comparable selection must be generated and separately reviewed.
