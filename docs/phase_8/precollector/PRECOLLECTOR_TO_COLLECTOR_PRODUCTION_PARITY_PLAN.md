# Pre-Collector to Collector Production Parity Plan

## Status

Owner-directed implementation plan for bringing the selected Pre-Collector lane to the same governed production state as the Collector lane.

This plan does not authorize forecasts, rankings, purchase recommendations, automatic execution, or UIP delivery by itself.

## Governing owner decision

- Analytical/reference universe: 94 products
- Investable universe: 83 products
- Reference-only universe: 11 products
- Reference-only products remain eligible for historical and comparable evidence use.
- Reference-only products are prohibited from entering buy rankings or purchase recommendations.
- Specialty products remain investable and must be modeled within appropriate specialty classes.
- Product price may affect forecast economics, affordability, liquidity, and ranking, but may not automatically remove a product.

## Collector parity target

The Collector authoritative production pipeline contains twelve stages:

1. Dynamic product discovery and admission
2. Canonical product registry
3. Current-price collection and reconciliation
4. Historical ledger construction and certification
5. Supply, demand, liquidity, and comparable evidence normalization
6. Forecast-method routing
7. Comparable selection where required
8. Method-aware forecast generation
9. Economic and semantic diagnostics
10. Purchase analysis
11. MTG export and UIP reconciliation
12. Owner acceptance and certification

Pre-Collector parity is achieved only when the selected Pre-Collector lane has equivalent governed artifacts and certification boundaries for all twelve stages.

## Current Pre-Collector completion state

### Stage 1 — Dynamic product discovery and admission

Status: COMPLETE FOR CURRENT BASELINE

- Full source universe inventoried.
- Pre-Collector scope controls applied.
- Canonical review universe established.
- Future discovery remains governed and dynamic.

### Stage 2 — Canonical product registry

Status: COMPLETE FOR CURRENT BASELINE

- 124 canonical products frozen.
- 94 analytical/reference products selected after current and historical evidence review.
- Owner disposition recorded: 83 investable and 11 reference-only.
- Product identity and TCGplayer identity crosswalks reconciled.

### Stage 3 — Current-price collection and reconciliation

Status: COMPLETE FOR CURRENT BASELINE

- Fresh current-price collection completed for 124 canonical products.
- 99 products current-price authorized.
- 94 selected analytical/reference products have current and historical authority.

### Stage 4 — Historical ledger construction and certification

Status: COMPLETE FOR CURRENT BASELINE

- 2 admitted historical sources.
- 2,826 canonical historical rows.
- 112 historically authorized canonical products.
- 94 selected analytical/reference products have both current and historical authority.

### Stage 5 — Supply, demand, liquidity, and comparable evidence normalization

Status: SUBSTANTIALLY COMPLETE; OWNER TAXONOMY APPROVAL REMAINS

- Certified eBay collection completed for all 94 selected products.
- 7,488 listings evaluated.
- 936 accepted listings.
- 67 direct-evidence routes proposed.
- 24 direct-history-limited routes proposed.
- 3 comparable-product-adjusted routes proposed.
- Five comparable candidates generated per product.
- Owner investable/reference disposition recorded.

Remaining Stage 5 requirement:

- certify economic product taxonomy and owner-approved comparable relationships;
- preserve specialty-family separation;
- prohibit reference-only products from ranking while permitting evidence contribution.

### Stage 6 — Forecast-method routing

Status: NOT CERTIFIED

Required outputs equivalent to Collector:

- Pre-Collector forecast-method route for each of the 94 analytical/reference products;
- explicit route reason and limitations;
- investable/reference-only flag;
- direct-history permission;
- comparable permission;
- forecast-output permission;
- purchase-analysis permission;
- purchase-recommendation authorization fixed false until later owner certification;
- fail-closed deferred routes where evidence or identity is not adequate.

Expected governed methods:

- DIRECT_HISTORY_CALIBRATED
- DIRECT_HISTORY_LIMITED
- COMPARABLE_PRODUCT_ADJUSTED
- FUNDAMENTAL_COMPARABLE_HYBRID, only if separately justified and owner approved
- DEFERRED_IDENTITY
- DEFERRED_MISSING_PRICE
- DEFERRED_INSUFFICIENT_EVIDENCE
- REFERENCE_ONLY_ANALYTICAL, for products prohibited from ranking and purchase analysis

### Stage 7 — Comparable selection where required

Status: NOT CERTIFIED

Required outputs equivalent to Collector:

- comparable target status;
- selected comparable rows;
- comparable-family classification;
- selection score and distance;
- price, era, lifecycle, product-family, supply, and liquidity similarity components;
- primary and secondary comparable designations;
- product-holdout enforcement;
- owner overrides with versioned reason codes;
- reference-only comparables clearly identified;
- no target may serve as its own comparable.

### Stage 8 — Method-aware forecast generation

Status: NOT STARTED / NOT AUTHORIZED

Required outputs equivalent to Collector production:

- one-, three-, and five-year forecasts;
- downside, base, and upside scenarios;
- direct-history and comparable-adjusted contributions;
- confidence penalties;
- uncertainty intervals;
- forecast lineage;
- method version;
- comparable contribution disclosure;
- no production promotion until historical tournament and calibration gates pass.

### Stage 9 — Economic and semantic diagnostics

Status: NOT STARTED

Required diagnostics:

- forecast reasonableness;
- extreme-value review queue;
- price discontinuity review;
- interval coverage and tail balance;
- family-level error;
- route-level error;
- stale evidence detection;
- implausible CAGR checks;
- price-versus-market mismatch;
- liquidity and fast-sale stress;
- manual-review queue;
- regression review against the prior certified baseline.

### Stage 10 — Purchase analysis

Status: NOT STARTED / NOT AUTHORIZED

Required outputs:

- fair-value range;
- net return after transaction costs;
- one-, three-, and five-year net CAGR;
- expected downside and probability of loss;
- liquidity-adjusted return;
- maximum sensible entry price;
- wait/entry-state analysis;
- rank inputs;
- reference-only products excluded;
- purchase recommendations remain blocked until separate certification.

### Stage 11 — MTG export and UIP reconciliation

Status: NOT STARTED FOR PRE-COLLECTOR PRODUCTION OUTPUTS

Required outputs:

- governed asset-master records;
- forecasts;
- recommendations, after authorization;
- risk metrics;
- source and lineage metadata;
- MTG package manifest;
- hashes;
- contract validation;
- dynamic UIP reconciliation;
- confirmation that UIP consumes but does not rewrite MTG analytical authority.

### Stage 12 — Owner acceptance and certification

Status: NOT STARTED

Required certification:

- structural reconciliation;
- data-quality review;
- economic and semantic review;
- forecast output acceptance;
- ranking and purchase-analysis acceptance;
- UIP reconciliation;
- clean repository;
- full regression suite;
- exact package hashes;
- explicit owner approval.

## Immediate authorized implementation block

The next implementation block is:

`PRECOLLECTOR_COMPARABLE_TAXONOMY_AND_METHOD_ROUTING`

It combines the remaining Stage 5 owner taxonomy work with Stage 6 routing preparation, but it must preserve separate certification artifacts.

### Block A — Owner taxonomy capture

Create and certify:

- `precollector_product_taxonomy.csv`
- `precollector_owner_comparable_decisions.csv`
- `precollector_reference_only_controls.csv`
- `precollector_specialty_family_controls.csv`
- taxonomy summary and manifest

### Block B — Forecast-method routing

Create and certify:

- `precollector_forecast_method_routes.csv`
- `precollector_forecast_method_route_summary.json`
- `precollector_forecast_method_route_manifest.json`
- route reconciliation and blocker report

### Block C — Comparable selection

Create and certify:

- `precollector_comparable_target_status.csv`
- `precollector_selected_comparables.csv`
- `precollector_comparable_selection_diagnostics.csv`
- comparable summary and manifest

## Required parity controls

- Use the Collector lane as the structural precedent, not as permission to reuse Collector-specific thresholds without review.
- Every Pre-Collector threshold, formula, weight, and override must be MTG-standard authorized or explicitly owner approved.
- No hard-coded universe counts in active production logic.
- No cross-lane identity borrowing.
- No reference-only product may receive a buy rank or purchase recommendation.
- Specialty products must retain family-aware comparability.
- Missing evidence lowers confidence or triggers a governed comparable route; it is not silently imputed.
- Product-level holdout is mandatory in comparable validation and model tournaments.
- Automated test success is necessary but insufficient.
- Forecasting, rankings, recommendations, automatic execution, and UIP delivery remain false until their respective certification gates pass.

## Completion definition

Selected Pre-Collectors reach Collector parity only when:

- all twelve stages have governed, versioned, reproducible outputs;
- every investable product reconciles across registry, model, history, evidence, method route, comparable selection, forecast, diagnostics, purchase analysis, and UIP export;
- all reference-only products remain analytically available but purchase-ineligible;
- all specialty products remain properly classified;
- production outputs pass structural, statistical, economic, semantic, regression, and owner-acceptance review;
- explicit owner certification authorizes the final production state.
