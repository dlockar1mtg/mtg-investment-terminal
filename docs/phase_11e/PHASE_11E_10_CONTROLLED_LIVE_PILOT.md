# Phase 11E.10 — Controlled Live Pilot and Promotion Certification

This milestone adds a live Browse adapter and a fail-closed four-product pilot runner.

## Certification

```powershell
python .\scripts\certify_phase_11e_10.py
```

Certification does not enable or execute live traffic.

## Readiness inspection

```powershell
python .\scripts\run_phase_11e_10_controlled_live_pilot.py --inspect
```

This checks credential availability and current Browse quota. It does not collect product listings.

## Live execution protections

Live execution requires all of the following:

1. readiness inspection must pass;
2. `MTG_EBAY_HISTORY_LIVE_ENABLED=true`;
3. exact confirmation token `EXECUTE-EBAY-HIST-001`;
4. an explicit `--execute` command.

Each attempt is preserved beneath a timestamped directory. Promotion remains `PENDING_MANUAL_REVIEW`; the runner never writes directly into governed history.


## Live pilot review hardening

The first preserved live attempt showed that generic edition names such as
`Unlimited Edition` and `Beta Edition` can return sealed products from unrelated
trading-card games. The initial attempt is therefore blocked from promotion.

The hardened policy now:

- requires a Magic-specific brand signal for booster-box products;
- prefixes live booster queries with `Magic The Gathering`;
- reclassifies the preserved attempt;
- requires a new controlled pilot attempt before promotion review.

Run the preserved-attempt review with:

```powershell
python .\scripts\review_phase_11e_10_live_pilot.py
```


## Query ladder hardening

The second pilot used a single exact quoted query and returned no listings for
all four products. The live collector now uses three Magic-specific query
variants per booster-box product:

1. `Magic The Gathering "<set>" booster box`
2. `MTG "<set>" booster box`
3. `Magic "<set>" sealed box`

Results are deduplicated by eBay item ID. The classifier still requires an MTG
brand signal, so broader retrieval does not weaken acceptance rules. Quota
preflight again reserves a maximum of three calls per product.
