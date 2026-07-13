# Secret Lair Foundation Architecture

Terminal 2.6.0 intentionally separates Secret Lair assets from booster-product
assumptions.

## Controlled flow

1. Curated CSV input
2. Normalization and deterministic ID assignment
3. Local working registry
4. Row-level quality findings
5. Seven warehouse datasets
6. Pricing integration in Terminal 2.6.1

## Asset identity

A Secret Lair investment asset is a distinct drop variant and finish. Foil and
nonfoil versions are separate assets. IDs are deterministic and remain stable
when the same source identity, drop, variant, and finish are re-imported.

## Data policy

The tracked template is schema-only. The local working registry is ignored by
Git so curated data can evolve independently from application code.
