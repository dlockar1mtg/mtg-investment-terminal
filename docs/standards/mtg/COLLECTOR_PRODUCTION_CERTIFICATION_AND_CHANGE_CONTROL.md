# Collector Production Certification and Change Control

## Authority

The Collector production pipeline is governed by the repository owner, Devon Lockard. No material change is approved merely because automated tests pass.

## Completion standard

Collector is certified only when all of the following are complete:

1. Structural tests pass.
2. The dynamic Collector universe reconciles without unexplained loss or duplication.
3. Current prices, historical prices, evidence signals, and forecast inputs have valid identity, source, date, freshness, and quality semantics.
4. Forecast outputs contain the required methods, horizons, scenarios, evidence lineage, confidence, uncertainty, and limitations.
5. Economic and semantic diagnostics show that the numbers are coherent and plausible.
6. Required human-review outputs have been inspected and accepted by Devon Lockard.
7. MTG-native outputs and the UIP delivery reconcile dynamically.
8. Unused or superseded implementation is archived or indexed so it remains recoverable and understandable.
9. Production documentation identifies the authoritative entry point, inputs, outputs, policies, tests, gates, and recovery paths.
10. A signed owner-approval record authorizes the certified version.

## Required output acceptance review

Certification must include, at minimum:

- product-universe reconciliation;
- current-price freshness and source review;
- historical coverage and anomaly review;
- method-routing reconciliation;
- comparable-selection review;
- forecast scenario ordering and horizon coherence;
- implied CAGR and extreme-value review;
- supply, demand, liquidity, lifecycle, and reprint adjustment review;
- confidence and uncertainty review;
- purchase-price and recommendation reasonableness review;
- MTG-to-UIP identity and semantic reconciliation.

Automated checks may prepare these reviews but do not replace owner inspection.

## Owner approval gate

The following changes require Devon Lockard's direct approval before certification or production use:

- forecasting methods, formulas, weights, caps, floors, thresholds, or horizons;
- source hierarchy, pricing semantics, or freshness rules;
- product-universe, identity, lane, or configuration rules;
- supply, demand, liquidity, reprint, lifecycle, or confidence methodology;
- forecast or purchase authorization rules;
- MTG or UIP schemas, adapters, manifests, or reconciliation rules;
- production entry points or authoritative output locations;
- removal, replacement, or archival of certified pipeline code;
- changes to this standard or its machine-readable policy.

Approval must be explicit and recorded in a versioned owner-approval artifact. Silence, a passing test suite, a merged dependency, or an automated tool action is not approval.

## Change process

1. Create a feature branch.
2. Record the proposed material changes and rationale.
3. Run structural, semantic, economic, and integration validation.
4. Produce before/after output comparisons.
5. Preserve or archive replaced implementation with provenance.
6. Obtain CODEOWNER review and explicit owner approval.
7. Merge only after approval.
8. Create a certification tag and immutable certification artifact.

## Preservation and recovery

Code or artifacts not used by the authoritative pipeline must not be silently deleted. Each item must be one of:

- active and authoritative;
- active supporting evidence;
- archived legacy implementation;
- historical certification evidence;
- explicitly approved for deletion after recovery is verified in Git history.

The production documentation must provide an index of archived or superseded pathways, their former purpose, replacement, reason for retirement, last certified version, and recovery location.

## GitHub enforcement

The repository uses CODEOWNERS to identify owner-controlled paths. The `main` branch should be configured to require:

- pull requests before merging;
- at least one approving review;
- CODEOWNER review;
- dismissal of stale approvals when new commits are pushed;
- required status checks;
- conversation resolution;
- no force pushes;
- no branch deletion;
- administrator enforcement where available.

GitHub branch protection supplies the enforcement layer. This document supplies the certification and approval contract.
