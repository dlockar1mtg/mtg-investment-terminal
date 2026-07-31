# Collector Historical Source Adjudication Candidate

## Purpose

The repository-wide inventory intentionally scans broadly. Its results are discovery evidence, not historical-source authority.

This adjudication layer narrows that inventory to Collector-specific candidate sources and records why other artifacts cannot be used for historical as-of reconstruction.

## Core rules

1. A current output is not historical evidence merely because it contains a date column.
2. Backups, repair inputs, package copies, dashboards, forecasts, rankings, recommendations, and other-lane files must not enter the Collector snapshot ledger.
3. Price history requires product identity, observation time, price lineage, and Collector coverage.
4. Identity may be bounded by governed release-date evidence, but present-day identity decisions must not be projected backward without temporal support.
5. Historical routes must be reconstructed from evidence available on the decision date.
6. Historical comparables must be recomputed from products and information available on the decision date.
7. Missing historical evidence remains visible; present-day evidence cannot silently replace it.

## Candidate hierarchy

The initial primary price-history candidate is the universal historical observation ledger, subject to schema, duplication, Collector coverage, and provenance review.

The universal MTG price-history file is supporting evidence only until duplication and lineage are reconciled.

The Collector governed registry and governed release-date evidence are candidate identity boundaries. They are not automatically treated as historically effective records.

Current product-master evidence, current routing outputs, and current comparable outputs remain reference-only until historical effective dates or time-correct reconstruction are available.

## Required review outputs

- Collector source adjudication table
- Rejection and reference-only log
- Role-coverage summary
- Explicit list of missing historical roles
- Selected primary and supporting sources with lineage

## Authorization boundary

This candidate does not authorize historical snapshot construction, forecasts, parameter changes, or purchase recommendations.
