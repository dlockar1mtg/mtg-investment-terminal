# Collector Deep-History Recovery Consolidated Batch

## Purpose

This batch determines whether the local repository contains price observations deep enough to support genuine chronological Collector walk-forward testing. It also repairs product-name and release-date resolution, including applied admissions not yet fully represented in the governed registry.

## Governing boundary

A historical price is not automatically a historically available model input. Recovered archive observations remain in `RETROSPECTIVE_AVAILABILITY_UNPROVEN` status until source lineage proves when the information became available. Such rows may support outcome measurement but may not enter historical forecasts.

## Batch outputs

The builder produces a local-source inventory, source schema profiles, resolved product identity and release metadata, a deduplicated deep-history candidate ledger, exclusions, per-product date coverage, and a summary decision package.

## Interpretation

- `deep_history_source_count > 0` means at least one locally present source contains governed Collector observations dated before July 1, 2026.
- `products_with_deep_history_count > 0` means historical price depth exists for at least part of the governed universe.
- `historical_decision_input_eligible_count` remains zero until knowledge availability is separately proven and owner-approved.
- Missing local sources are surfaced and never silently replaced.
- Missing release dates remain visible and prevent release-boundary certification.

## Next milestone

When deep history exists, the next consolidated batch will adjudicate source lineage, establish an owner-reviewable knowledge-availability policy, build historical as-of snapshots, reconstruct routes and comparables, and create the first candidate walk-forward dataset. When deep history does not exist, the platform must explicitly distinguish prospective model validation from retrospective outcome analysis and define an ongoing snapshot-capture program.
