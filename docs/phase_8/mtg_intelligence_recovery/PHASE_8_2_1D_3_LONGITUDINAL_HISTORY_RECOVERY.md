# Phase 8.2.1D.3 — Longitudinal Secret Lair History Recovery

This package repairs the D.2 source-selection error.

The repository already contains a likely longitudinal archive:

`data/operations/mtg_tcgcsv_price_backfill/archive/tcgcsv_monthly_archive_observations.csv`

The discovery inventory reported roughly 17,000 rows and hundreds of Secret Lair identifiers in that archive, while D.2 used only the current one-date warehouse snapshot.

## Safety design

The recovery process does not initially overwrite the warehouse source.

It first:

1. normalizes the archive and current snapshot;
2. rejects ungoverned, undated, or nonpositive observations;
3. deduplicates product/date/source observations using a median;
4. creates a candidate canonical history;
5. proves that the current snapshot is preserved;
6. runs the D.2 historical-performance engine in isolated validation folders;
7. requires historical-ready products and preserved forecast boundaries.

Promotion is a separate command and requires both certifications.

## No-loss rule

The candidate must preserve every valid current snapshot observation while adding longitudinal archive coverage. It must produce at least one product with two dates spanning 30 days before promotion is allowed.
