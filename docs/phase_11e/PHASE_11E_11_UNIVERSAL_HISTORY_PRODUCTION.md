# Phase 11E.11 — Universal Historical Completion Production Cycle

One production command rebuilds the governed 1,141-product historical ledger and collects a current-market eBay snapshot for all 152 eBay-routed products.

The eBay Browse snapshot is explicitly classified as current asking-market evidence, not historical sold-price evidence.

## Certification

```powershell
python .\scripts\certify_phase_11e_11.py
```

## Readiness

```powershell
python .\scripts\run_universal_mtg_history_production.py --inspect
```

## Production

```powershell
$env:MTG_EBAY_HISTORY_LIVE_ENABLED = "true"
python .\scripts\run_universal_mtg_history_production.py --execute --confirmation EXECUTE-UNIVERSAL-MTG-PRODUCTION
Remove-Item Env:\MTG_EBAY_HISTORY_LIVE_ENABLED
```

The production runner checkpoints every product and supports `--resume-attempt <path>` after interruption.
