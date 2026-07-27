# Phase 10.18 — eBay Matching Precision Hardening

## Purpose

Improve eBay product matching without consuming additional eBay API quota. Phase 10.18 replays previously collected listing evidence through a deterministic identity layer that distinguishes product form, finish, and canonical product identity.

## Scope

- Booster display versus single pack, loose pack, case, or incomplete box
- Secret Lair bundle versus individual drop
- Commander deck and deck-product enforcement
- Kit-product enforcement
- Traditional foil, rainbow foil, double-rainbow foil, galaxy foil, etched foil, raised foil, confetti foil, and nonfoil separation
- Machine-readable identity reason codes
- Offline replay across saved workflow artifacts
- Before/after transition reports

## Safety and quota governance

The offline replay script performs no network operations and records `quota_calls: 0`. Live collection must remain paused until offline regression evidence is reviewed and accepted.

## Components

- `terminal2/market_sources/ebay_product_identity.py`
- `terminal2/market_sources/ebay_precision_v2.py`
- `scripts/replay_ebay_matching_offline.py`
- `tests/test_ebay_product_identity.py`
- `tests/test_ebay_offline_replay.py`

## Execution

```powershell
python scripts\replay_ebay_matching_offline.py `
  --input-root data\operations\phase_10_18\source_artifacts `
  --output-root data\operations\phase_10_18\offline_replay
```

The input root may contain multiple extracted GitHub Actions artifacts. The script recursively locates `ebay_listing_match_results_*.csv` files.

## Outputs

Each replay creates a timestamped folder containing:

- `ebay_offline_reclassified_listings.csv`
- `ebay_offline_changed_listings.csv`
- `ebay_offline_product_summary.csv`
- `ebay_offline_replay_summary.json`

## Certification gates

Phase 10.18 may proceed to a live canary only when:

1. All identity and replay tests pass.
2. Replay reports `quota_calls: 0`.
3. Known wrong-finish, wrong-form, single-pack, component, and sibling-product listings are downgraded.
4. No unexplained accepted-listing upgrades occur.
5. Changed rows are auditable through reason codes.
6. A targeted canary is limited to previously weak products.

## Live activation boundary

This phase does not replace the live matcher automatically. `ebay_precision_v2.py` remains an offline certification layer until historical replay results are reviewed and a separate activation change is approved.
