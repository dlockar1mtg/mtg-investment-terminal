# Collector Candidate Calculator Input Discovery Gate

## Purpose

Before the non-production Collector candidate calculator is connected to operational data, the repository must discover and profile the actual locally generated route, evidence, history, and comparable files.

This avoids guessing file names, schemas, row counts, or column availability.

## Governing boundary

The discovery audit:

- does not calculate forecasts;
- does not alter methodology;
- does not activate the numeric candidate;
- does not authorize projections;
- does not authorize purchase recommendations;
- does not convert observed row counts into permanent controls.

## Required input families

The calculator requires current local artifacts for:

1. Collector forecast-method routes;
2. normalized Collector evidence;
3. Collector historical evidence or certification output;
4. selected Collector comparables;
5. the inactive numeric candidate configuration;
6. the conceptual owner-approval artifact.

Comparable target status is profiled when available but is not treated as a separate hard requirement when selected-comparable output and the governed hybrid override provide the applicable evidence chain.

## Output

The audit writes:

- `collector_candidate_input_inventory.json`
- `collector_candidate_input_audit_summary.json`

under:

`data/operations/collector_candidate_calculator/input_audit_v1_0_0`

The inventory records actual paths, modification times, file sizes, CSV row counts, CSV columns, and JSON top-level keys.

## Next gate

The non-production calculator may be implemented only after the discovered schemas are reviewed and mapped explicitly. Missing fields must remain visible; they may not be silently replaced with invented defaults that change methodology.
