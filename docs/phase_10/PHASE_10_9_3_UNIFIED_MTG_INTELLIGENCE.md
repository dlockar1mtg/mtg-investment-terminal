# Phase 10.9.3 — Unified MTG Forecast and Recommendation Interface

## Objective

Expose one deterministic intelligence interface across the three certified MTG production lanes without changing or fabricating their native forecast models.

## Certified input universe

- Secret Lairs: 973
- Collector Booster Boxes: 49
- Pre-Collector Booster Boxes: 119
- Total: 1,141

## Design

The interface preserves both supported forecast shapes:

1. Secret Lair native guarded forecasts use generic low, base, and high values.
2. Booster Box forecasts use explicit 1-year, 3-year, and 5-year downside, base, and upside values.

The unified output therefore contains both native forecast fields and horizon-specific fields. Unsupported fields remain blank rather than being inferred or copied into an artificial horizon.

## Unified fields

The output includes:

- Universal and source identities
- Lane and product class
- Admission and quality states
- Current market value
- Forecast method, status, and normalized eligibility
- Native low/base/high forecast values
- 1-year, 3-year, and 5-year forecast values
- Recommendation action, status, and normalized eligibility
- Confidence, rationale, and suppression reason
- Currency

## Certification requirements

- Exactly 1,141 output rows
- Exact lane counts: 973 / 49 / 119
- Unique universal product IDs
- Zero missing source joins
- USD currency on every row
- Explicit YES/NO forecast and recommendation eligibility
- Secret Lair numeric forecasts: 973
- Collector Booster Box numeric forecasts: 47
- Collector Booster Box recommendation eligible: 36
- Pre-Collector Booster Box numeric forecasts: 83
- Pre-Collector Booster Box recommendation eligible: 65
- No private holdings fields
- Zero API quota calls

## Generated outputs

Generated locally under:

`data/validation/phase_10/unified_mtg_intelligence/`

- `unified_mtg_intelligence_interface.csv`
- `unified_mtg_intelligence_diagnostics.csv`
- `unified_mtg_intelligence_manifest.json`
- `PHASE_10_9_3_UNIFIED_MTG_INTELLIGENCE_CERTIFICATION.md`

Generated outputs remain local and must not be staged.

## Execution

```powershell
powershell -ExecutionPolicy Bypass `
    -File `
    ".\scripts\run_phase_10_9_3_unified_mtg_intelligence.ps1"
```
