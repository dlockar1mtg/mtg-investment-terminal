# Phase 10.9.4 — Unified MTG Production Closeout

## Purpose

Certify the Phase 10.9 unified MTG product registry, owned portfolio, and intelligence interface as one production-ready package.

## Certified structural targets

- Unified products: 1,141
- Secret Lairs: 973
- Collector Booster Boxes: 49
- Pre-Collector Booster Boxes: 119
- Owned positions: 14
- Secret Lair positions: 12
- Collector Booster Box positions: 2
- Pre-Collector Booster Box positions: 0
- API quota calls: 0

## Required inputs

- `data/validation/phase_10/unified_mtg_registry/unified_mtg_product_registry.csv`
- `data/validation/phase_10/unified_mtg_registry/unified_mtg_product_registry_manifest.json`
- `data/validation/phase_10/unified_mtg_portfolio/unified_mtg_owned_positions.csv`
- `data/validation/phase_10/unified_mtg_portfolio/unified_mtg_portfolio_manifest.json`
- `data/validation/phase_10/unified_mtg_intelligence/unified_mtg_intelligence_interface.csv`
- `data/validation/phase_10/unified_mtg_intelligence/unified_mtg_intelligence_manifest.json`

## Execution

```powershell
powershell -ExecutionPolicy Bypass `
    -File `
    ".\scripts\run_phase_10_9_4_unified_mtg_closeout.ps1"
```

The runner performs:

1. Focused Phase 10.9 tests.
2. Broader Secret Lair, Collector Booster Box, and Pre-Collector production tests.
3. Cross-artifact identity and count reconciliation.
4. Portfolio financial reconciliation.
5. Artifact SHA-256 validation.
6. Privacy and quota checks.
7. Generation of a tracked commit allowlist.

## Required status

```text
PHASE 10.9.4 UNIFIED MTG PRODUCTION CLOSEOUT: PRODUCTION_CLOSED
```

## Commit policy

Generated files under `data/validation/phase_10/` remain local. Personal holdings, generated registries, intelligence exports, manifests, diagnostics, caches, databases, and archives must not be staged.

Use only the generated tracked allowlist. Never use `git add .`.
