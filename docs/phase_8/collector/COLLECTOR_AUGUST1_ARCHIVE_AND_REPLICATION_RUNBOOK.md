# Collector August 1 Archive and Replication Runbook

## Document control

- Repository: `dlockar1mtg/mtg-investment-terminal`
- Branch: `phase-8.2.8a-august1-snapshot-bound-current-product-rebuild`
- Operating snapshot: `collector-20260801T211201Z-7688afbd`
- Operating date: `2026-08-01`
- Operating timezone: `America/Chicago`
- Source bundle SHA-256: `7688afbd6dfb4483c0a316dad6a2a05458944434a91a3f714568e5f4a10c7890`
- Purpose: preserve the Collector Booster process, its evidence chain, its final outputs, and the procedure needed to reproduce the same governed workflow for Pre-Collector Booster products and Secret Lairs.

## Governance warning

The canonical MTG standard requires approval, a version change, and recertification whenever methods, weights, thresholds, source hierarchy, product universe, or eligibility rules change. The Collector ranking and purchase policies therefore must not be copied blindly to another product class. They may be used as a structural template, but Pre-Collector and Secret Lair policies require explicit owner approval after their own evidence review.

The process must keep these authorities separate:

1. Source and identity authority.
2. Historical and comparable evidence authority.
3. Forecast authority.
4. Calibration and reasonableness evidence.
5. Ranking eligibility.
6. Ranking policy and ranked output.
7. Purchase recommendation policy and output.
8. Automatic execution authorization, which remains separate and disabled unless explicitly approved.

## Certified Collector baseline

The final Collector chain preserved the following counts:

| Authority | Final count |
|---|---:|
| Current-price products | 50 |
| Historical ledger rows | 1,215 |
| Integrated comparable rows | 121 |
| Forecast products | 49 |
| Forecast rows | 294 |
| Forecast lineage rows | 294 |
| Blocked horizons | 6 |
| Total product/horizon coverage | 300 |
| Calibration rows | 294 |
| Ranking eligibility rows | 49 |
| Final ranking rows | 49 |
| Purchase authority rows | 49 |
| Authorized purchase candidates | 13 |
| Watchlist products | 33 |
| Not purchase eligible | 3 |

Purchase status distribution:

- `STRONG_PURCHASE_CANDIDATE`: 7
- `PURCHASE_CANDIDATE`: 6
- `WATCHLIST`: 33
- `NOT_PURCHASE_ELIGIBLE`: 3

Final safety controls:

- Conditional products purchase-authorized: 0
- Forecast values modified by purchase stage: 0
- Automatic purchase execution authorized: false
- Critical failures: 0

## Evidence and authority chain

### 1. Original August 1 evidence

Exact evidence files used by the final binding gate:

- `data/governance/permanence/certification/collector_v1_august_1_snapshot_registration/collector_v1_august_1_snapshot_registration_summary.json`
- `data/governance/permanence/certification/collector_v1_snapshot_bound_authority_verification/collector_v1_snapshot_bound_authority_verification_summary.json`

The binding gate verified:

- exact snapshot identity;
- exact source-bundle SHA-256;
- model-input certification;
- model-rebuild authorization;
- no structured failure status;
- no nonempty `critical_failures` collection.

### 2. Final source and routing authorities

- Current price: `data/governance/permanence/certification/collector_v1_final_premodel_user_exclusion_resolution/collector_final_current_price_authority.csv`
- Method routing: `data/governance/permanence/certification/collector_v1_final_premodel_user_exclusion_resolution/collector_final_method_routing.csv`
- Historical ledger: `data/governance/permanence/certification/collector_v1_august1_historical_observation_ledger/collector_august1_historical_observation_ledger.csv`
- Integrated comparables: `data/governance/permanence/certification/collector_v1_lorwyn_comparable_authority_integration/collector_integrated_comparable_pool_authority.csv`
- Current supply: `data/governance/permanence/certification/collector_v1_august1_current_data_package/collector_ebay_product_supply_snapshot.csv`

### 3. Final forecast authorities

- Forecasts: `data/governance/permanence/certification/collector_v1_canonical_identity_lineage_recertification/collector_final_authority_bound_49_product_forecasts.csv`
- Lineage: `data/governance/permanence/certification/collector_v1_canonical_identity_lineage_recertification/collector_final_forecast_source_identity_lineage_manifest.csv`
- Blocked horizons: `data/governance/permanence/certification/collector_v1_canonical_identity_lineage_recertification/collector_final_authority_bound_blocked_horizons.csv`
- Canonical summary: `data/governance/permanence/certification/collector_v1_canonical_identity_lineage_recertification/collector_canonical_identity_lineage_recertification_summary.json`

### 4. Calibration and ranking authorities

- Calibration: `data/governance/permanence/certification/collector_v1_final_probabilistic_calibration/collector_final_forecast_row_validation.csv`
- Ranking eligibility: `data/governance/permanence/certification/collector_v1_final_ranking_eligibility/collector_final_ranking_eligibility_authority.csv`
- Final ranking: `data/governance/permanence/certification/collector_v1_final_governed_ranking/collector_final_governed_1_49_rankings.csv`
- Ranking summary: `data/governance/permanence/certification/collector_v1_final_governed_ranking/collector_final_governed_ranking_summary.json`

### 5. Purchase authorities

- Summary: `data/governance/permanence/certification/collector_v1_purchase_recommendation_certification/collector_purchase_recommendation_summary.json`
- Complete authority: `data/governance/permanence/certification/collector_v1_purchase_recommendation_certification/collector_purchase_recommendation_authority.csv`
- Authorized subset: `data/governance/permanence/certification/collector_v1_purchase_recommendation_certification/collector_authorized_purchase_candidates.csv`
- Watchlist subset: `data/governance/permanence/certification/collector_v1_purchase_recommendation_certification/collector_purchase_watchlist.csv`

## Collector policy snapshot

The following is an archive of the Collector policy used for this run, not an automatic policy for other MTG product classes.

### Ranking structure

Primary horizons:

- 365 days
- 1,095 days

Collector ranking weights:

| Factor | Weight |
|---|---:|
| 365-day forecast return | 0.30 |
| 1,095-day annualized forecast return | 0.10 |
| Early opportunity | 0.15 |
| Downside protection | 0.15 |
| Uncertainty control | 0.10 |
| Supply and demand | 0.10 |
| Calibration strength | 0.10 |

Ranking controls:

- full 49-product competition;
- primary-horizon rows required;
- cross-sectional percentile normalization;
- eligibility penalties applied;
- deterministic tie breaker: `canonical_product_id`;
- conditional products remain purchase-ineligible;
- forecast values are not modified by ranking.

### Purchase structure

Strong candidate rules used in the Collector run:

- rank 1 through 10;
- governed score at least 65;
- 365-day probability of loss no more than 5%;
- probability of a 50% gain at least 45%;
- current price at least 10% below the 365-day p25 forecast;
- evidence status purchase-eligible.

Strong entry ceiling:

`365-day p25 forecast price / 1.10`

Standard candidate rules used in the Collector run:

- rank 1 through 15;
- governed score at least 58;
- 365-day probability of loss no more than 8%;
- current price no higher than the 365-day p25 forecast;
- evidence status purchase-eligible.

Candidate entry ceiling:

`365-day p25 forecast price`

These rules require owner review before reuse for Pre-Collectors or Secret Lairs.

## End-to-end Collector execution sequence

### Phase A — Freeze and identify the operating snapshot

1. Freeze the source package.
2. Record snapshot ID, operating date, timezone, and source-bundle SHA-256.
3. Verify model-input certification and rebuild authorization.
4. Fail closed on identity, executable-price, source, or parse failures.

### Phase B — Build source authorities

1. Reconcile canonical identity.
2. Establish current-price authority.
3. Establish release-date authority.
4. Build historical observation ledger.
5. Build current-supply authority.
6. Resolve product exclusions explicitly.
7. Record every source path and hash.

### Phase C — Build product-specific forecasting evidence

1. Determine direct-history eligibility by product and horizon.
2. Build governed comparable pools where direct history is insufficient.
3. Preserve limited-history and deferred reasons.
4. Generate probabilistic forecasts with explicit method identifiers.
5. Produce one row per product and required horizon.
6. Generate lineage for every forecast row.
7. Create explicit blocked-horizon rows for products without forecasts.

### Phase D — Validate forecasts

1. Check row counts and unique product/horizon keys.
2. Check p10/p25/median/p75/p90 ordering.
3. Check current-price consistency.
4. Check method, evidence, uncertainty, limitations, source, and version disclosure.
5. Run calibration and reasonableness checks.
6. Preserve review queues and limitations; do not silently repair forecast values.

### Phase E — Approve ranking policy

Before ranking another product class, explicitly approve:

- competition universe;
- primary horizons;
- factor definitions;
- weights;
- normalization;
- penalties;
- eligibility statuses;
- tie breaker;
- treatment of limited and conditional evidence.

Only then version the contract and execute ranking.

### Phase F — Approve purchase policy

Before purchase recommendations for another product class, explicitly approve:

- rank cutoffs;
- governed-score cutoffs;
- downside limits;
- gain-probability requirements;
- entry-margin rules;
- maximum quantities;
- price freshness requirements;
- human-review requirements.

Purchase authorization must remain separate from ranking and automatic execution.

### Phase G — Independent audit

1. Inventory all output files.
2. Parse all JSON and CSV files.
3. Confirm unique CSV headers.
4. Recount final authorities independently.
5. Reconcile every declared authority hash after the full inventory is built.
6. Compare implementation to exact canonical MTG-standard clauses.
7. Verify conditional products are not purchase-authorized.
8. Verify forecast values are not changed downstream.
9. Verify automatic execution remains false.
10. Bind the audit to exact original evidence files.

### Phase H — Human-readable review

Create a review workbook with:

- Dashboard
- Authorized candidates
- Complete product authority
- Watchlist
- Consistency audit
- Methodology

Required consistency checks:

- aggregate counts equal the certification summary;
- authorized and watchlist subsets match the complete authority;
- candidate ceiling equals p25;
- strong ceiling equals p25 divided by 1.10;
- median return equals median price divided by current price minus 1;
- p25 is no greater than median, and median is no greater than p90;
- authorization agrees with purchase status;
- quantity is 1 only for authorized rows;
- budget band agrees with current price.

## Replication plan for Pre-Collector Booster products

Pre-Collector Booster products should use the same eight-phase workflow, but must have their own:

- canonical product universe;
- product-definition rule;
- source hierarchy;
- sealed-product price authority;
- historical-price reconstruction method;
- supply proxy;
- comparable taxonomy;
- lifecycle features;
- required horizons;
- calibration windows;
- ranking weights and penalties;
- purchase thresholds.

Key Pre-Collector questions that must be answered before implementation:

1. What exact product years and box types define the universe?
2. Are foreign-language, first-edition, unlimited, and specialty boxes separate assets?
3. Which source is authoritative for executable sealed-box prices?
4. How are sparse sales and condition differences handled?
5. Which eras are valid comparables?
6. How are reserve-list exposure, print-run scarcity, and authentication risk represented?
7. Which liquidity measure replaces modern eBay listing depth?
8. Are one-, three-, and five-year horizons still appropriate?

## Replication plan for Secret Lairs

Secret Lairs require the same governance stages but a different asset model. Each drop must define:

- sealed versus opened status;
- foil versus nonfoil variant;
- drop, bundle, and individual SKU identity;
- sale window and delivery date;
- original sale price and fees;
- print-to-demand versus limited-run structure;
- reprint and card-demand exposure;
- artist/IP/crossover attributes;
- supply and listing-depth measures;
- liquidity and transaction-cost treatment.

Key Secret Lair questions that must be answered before implementation:

1. Is the governed asset a sealed drop, bundle, or individual SKU?
2. How are foil and nonfoil versions separated?
3. How are delayed fulfillment and sale-window timing treated?
4. Which marketplaces are authoritative for current price and realized sales?
5. How are reprints and card-level demand incorporated?
6. How is print-to-demand status represented?
7. Which comparable groups are legitimate across IP, artist, theme, and card composition?
8. What minimum liquidity is required for purchase eligibility?

## Fail-closed PowerShell standard

Interactive PowerShell must not use `exit`, because it closes the user’s PowerShell window. Use a guarded script block with `throw`, or a committed runner that returns a process exit code.

Do not paste independent commands after a thrown exception and then rely on later green messages. A final certification message may print only inside the same guarded block after every required check passes.

Recommended pattern:

```powershell
& {
    $ErrorActionPreference = "Stop"

    function Stop-GovernedRun {
        param([string]$Message, [int]$Code)
        Write-Host $Message -ForegroundColor Red
        throw "GOVERNED_RUN_FAILED_$Code"
    }

    # Run checks.
    # Call Stop-GovernedRun immediately on failure.
    # Print final certification only after all checks pass.
}
```

## Archive completion checklist

Before closing a product-class project, verify that the archive includes:

- [ ] snapshot registration and source hash;
- [ ] exact evidence files;
- [ ] source and identity authorities;
- [ ] historical and comparable authorities;
- [ ] final forecasts and blocked rows;
- [ ] complete lineage;
- [ ] calibration and review outputs;
- [ ] approved ranking contract and output;
- [ ] approved purchase contract and output;
- [ ] end-to-end audit outputs;
- [ ] review workbook;
- [ ] full regression result;
- [ ] clean Git status;
- [ ] branch and commit references;
- [ ] explicit list of owner-approved policy decisions;
- [ ] new-chat handoff prompt.

## Current handoff state

Completed:

- Collector source through purchase authorities.
- Exact August 1 evidence binding.
- Twenty-one of twenty-one hash reconciliation.
- Eleven-clause MTG-standard review.
- Human-readable review workbook and row-level consistency audit.

Still required outside the model:

- Final human selection of actual purchase.
- Explicit approval of any policy reused or modified for Pre-Collectors or Secret Lairs.
