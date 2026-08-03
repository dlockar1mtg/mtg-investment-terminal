# MTG Data Permanence Master Plan

## Purpose

This program replaces recurring cleanup with a permanent, fail-closed data architecture. Its governing rule is:

> No downstream process may delete, overwrite, shorten, silently remap, substitute, or write backward into project data.

Forecast development remains stopped until the read-only certified-data boundary is operational and independently tested.

## Execution blocks

### Foundation Block — Phases 0–3

1. Preserve and inventory every current file without deletion.
2. Enforce the machine-readable data preservation constitution.
3. Establish immutable raw-vault conventions and append-only ingestion manifests.
4. Establish dataset registry and lineage records.

### Authority Block — Phases 4–7

5. Build the governed identity authority and versioned alias decisions.
6. Reconstruct the authoritative product-month history from preserved observations.
7. Independently certify preservation, identity, continuity, uniqueness, lineage, and conflicts.
8. Enforce a read-only certified-data boundary and path/hash validation.

### Recovery Block — Phases 8–9

9. Trace every prior forecast to exact inputs and classify its blast radius.
10. Rerun affected forecasts only from certified dataset IDs and hashes.

### Permanence Block — Phases 10–11

11. Add products and sources only through versioned candidate builds and atomic promotion.
12. Prove backup restoration, rollback, corruption rejection, and reproducibility.

## Phase exit gates

### Phase 0 — Preserve and inventory

- Full file inventory exists.
- SHA-256 exists for every readable file.
- No file is deleted or moved.
- Current model outputs are classified as VALID, UNVERIFIED, INVALIDATED, or QUARANTINED.
- Stop-the-line remains active.

### Phase 1 — Data preservation constitution

- Constitution is machine-readable.
- Forbidden operations and stop conditions are explicit.
- No authorization gate is opened.

### Phase 2 — Immutable source vault

- Vault paths are append-only and ingestion-specific.
- Each ingestion has source metadata, manifest, and checksums.
- Existing ingestion IDs cannot be overwritten.
- A second independent backup is documented and verified.

### Phase 3 — Dataset registry and lineage

- Every consumable dataset has an ID, version, state, hash, builder commit, and parent hashes.
- Unregistered datasets cannot be consumed by models.
- Descendant impact can be calculated from the registry.

### Phase 4 — Governed identity authority

- Every recognized historical row maps to a governed identity or explicit quarantine.
- Alias changes are versioned.
- Ambiguous Box, Display, Case, Pack, language, edition, and configuration mappings are never guessed.

### Phase 5 — Authoritative historical panel

- All raw observations remain preserved.
- Analytical product-month selection uses explicit source precedence.
- Duplicate and conflicting observations are retained in ledgers.
- No unexplained history truncation or identity split remains.

### Phase 6 — Independent certification

- Builder and certifier are separate processes.
- Accounting, identity, continuity, uniqueness, lineage, and conflict checks pass.
- Failed candidates cannot be promoted.

### Phase 7 — Read-only certified boundary

- Model processes cannot write to raw, governed, or certified locations.
- Models accept only certified dataset IDs and exact hashes.
- Unexpected paths and hash mismatches fail immediately.

### Phase 8 — Forecast blast-radius assessment

- Every prior model output is traced to exact parent datasets.
- Affected outputs are invalidated or marked reusable-code-only.
- Unaffected outputs require evidence of independent certified lineage.

### Phase 9 — Governed forecast rebuild

- All affected performance numbers are regenerated.
- Every run records code commit, configuration hash, dataset IDs, and dataset hashes.
- No methodology or purchase authorization is automatic.

### Phase 10 — Controlled growth

- New data creates a new version, never a destructive update.
- Product counts remain dynamic.
- Old histories cannot be altered by new products or sources.

### Phase 11 — Disaster recovery proof

- Local loss is restored from an independent backup.
- Hash verification passes after restore.
- Earlier certified versions can be restored.
- Corrupted candidates and identity regressions are rejected.
- A historical model run can be reproduced from its manifest.

## Definition of final

A component is final only when it is immutable, versioned, hashed, lineage-complete, identity-complete, row-preserving, continuity-certified, conflict-governed, atomically promoted, rollback-capable, and restore-tested.

## Current authorization state

- Forecasting resume: not authorized.
- Production projections: not authorized.
- Purchase recommendations: not authorized.
- Automatic model updates: not authorized.
- Technical freeze: not authorized.
- UIP acceptance: not authorized.
