# Phase 11E.9 — Governed eBay History Production Pipeline

This milestone certifies the complete offline path required before any live eBay historical accumulation.

## Scope

- collector interface
- offline replay collector
- listing acceptance and rejection rules
- replay artifact generation
- product coverage generation
- duplicate-safe consolidation simulation
- focused certification runner
- live execution disabled

## Certification command

```powershell
python .\scripts\certify_phase_11e_9.py
```

## Required outcome

The certification must report `PASS`, four matched pilot products, eight rejected unsafe listings, duplicate-safe consolidation, and `live_execution_enabled=false`.

No live API call is performed by this milestone.
