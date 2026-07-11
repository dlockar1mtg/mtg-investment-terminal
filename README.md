# MTG Investment Terminal v13.2

## Main v13.2 Fix: TCGCSV Archive Download Headers

v13.1 used Python's default `urllib` request when downloading TCGCSV archives. TCGCSV's FAQ asks automated users to send a clearly identifiable `User-Agent`, and the default Python request can return:

```text
HTTP Error 401: Unauthorized
```

v13.2 updates:

```text
backfill_tcgcsv_monthly_history.py
```

to send:

```text
User-Agent: MTGInvestmentTerminal/13.2 (historical archive backfill; personal use)
Accept: application/octet-stream,*/*;q=0.8
Referer: https://tcgcsv.com/faq
```

## Run

```bash
python backfill_tcgcsv_monthly_history.py
```

Then:

```bash
python import_historical_prices.py
python review_historical_database.py
python run.py
```

## If 401 still happens

Open one of the archive URLs directly in your browser:

```text
https://tcgcsv.com/archive/tcgplayer/prices-2024-02-08.ppmd.7z
```

If the browser also fails, TCGCSV may have temporarily restricted historical archive access. If the browser works but Python fails, download the monthly `.7z` files manually into:

```text
data/historical_imports/tcgcsv_archives/
```

Then rerun:

```bash
python backfill_tcgcsv_monthly_history.py
```

The script will use cached archive files when present.


# MTG Investment Terminal v13.1

## Main v13.1 Upgrade: Automated Monthly TCGCSV Archive Backfill

v13.1 adds:

```text
backfill_tcgcsv_monthly_history.py
```

This script downloads monthly TCGCSV archive files, extracts them with 7-Zip, filters price rows to your approved Product Master product IDs, and writes:

```text
data/historical_imports/historical_price_import.csv
```

Then the existing v13 importer can load those rows into the market database.

## Why this matters

TCGCSV has daily compressed historical price archives from February 8, 2024 onward. v13.1 uses monthly snapshots so you can quickly seed the model with historical price data without downloading hundreds of daily archives.

## Requirements

Install 7-Zip.

Windows default path is usually:

```text
C:\Program Files\7-Zip\7z.exe
```

The script will also work if `7z` is available on your PATH.

## Recommended workflow

First run the normal pipeline so Product Master exists:

```bash
python reset_source_cache.py
python run.py
```

Then run the monthly backfill:

```bash
python backfill_tcgcsv_monthly_history.py
```

Then import the generated file:

```bash
python import_historical_prices.py
python review_historical_database.py
python run.py
```

## Optional date range

```bash
python backfill_tcgcsv_monthly_history.py --start 2024-02-08 --end 2026-07-01
```

## Output files

```text
data/historical_imports/historical_price_import.csv
data/historical_imports/audit/tcgcsv_monthly_backfill_audit.csv
data/historical_imports/tcgcsv_archives/
data/historical_imports/tcgcsv_extracted/
```

## Notes

The script uses the Product Master fields:

```text
investment_product_id
approved_tcgplayer_product_id
tcgcsv_category_id
tcgcsv_group_id
box_name
set_name
```

It then looks inside each extracted archive at:

```text
YYYY-MM-DD/<tcgcsv_category_id>/<tcgcsv_group_id>/prices
```

and matches rows by `productId`.


# MTG Investment Terminal v13

## Main v13 Upgrade: Historical Price Importer

v13 keeps the stable v12.1 pipeline and adds tooling to backfill/import historical prices into the market database.

This solves the main limitation from v12.1:

```text
observations = 1
return_30d = NaN
return_90d = NaN
```

With a historical import, the model can immediately calculate:

- 7/14/30/60/90/180/365-day moving averages
- 30/90/180/365-day returns
- all-time high / all-time low
- drawdown from ATH
- annualized volatility
- richer Monte Carlo inputs

## New Files

```text
models/historical_importer.py
create_historical_import_template.py
import_historical_prices.py
review_historical_database.py
generate_sample_history.py
data/historical_imports/historical_price_import_template.csv
data/historical_imports/historical_price_import.csv
data/historical_imports/historical_import_audit.csv
```

## Recommended workflow

First run the normal pipeline once:

```bash
python reset_source_cache.py
python run.py
```

Create an import template:

```bash
python create_historical_import_template.py
```

Fill this file with real historical prices:

```text
data/historical_imports/historical_price_import.csv
```

Required columns:

```text
observation_date
investment_product_id
tcgplayer_product_id
box_name
set_name
current_price
low_price
price_source
price_data_quality
```

Import history:

```bash
python import_historical_prices.py
python review_historical_database.py
python run.py
```

## Optional test workflow

To test the historical metrics immediately with fake sample data:

```bash
python generate_sample_history.py
python import_historical_prices.py
python review_historical_database.py
python run.py
```

Do not use synthetic history for real investment decisions. It is only for testing that the metric engine works.

## Why this matters

The platform is now database-first:

```text
Product master
↓
Daily prices
↓
Historical import
↓
Rolling metrics
↓
Real signals
↓
Market intelligence
↓
Monte Carlo
↓
Ranking
```

As you import or accumulate price history, the model becomes more data-driven instead of relying mostly on static assumptions.


# MTG Investment Terminal v12.1

## Stability Patch

v12.1 fixes the v12 pipeline failure:

```text
'int' object has no attribute 'fillna'
```

## What changed

- Replaced fragile scalar/Series handling in `models/market_database.py`.
- Replaced `update_prices.py` with explicit stage-by-stage validation.
- The pipeline now stops clearly if a stage produces zero rows.
- Added `validate_v12_1_pipeline.py`.

## Expected successful run

After:

```bash
python reset_source_cache.py
python run.py
```

you should see stage messages like:

```text
Stage OK: TCGCSV discovery rows=...
Stage OK: Approved product master selection rows=...
Stage OK: Investment feature build rows=...
Stage OK: Rolling market database metrics rows=...
Stage OK: Real signal engine rows=...
Stage OK: Market intelligence + Monte Carlo rows=...
```

Then run:

```bash
python validate_v12_1_pipeline.py
python review_real_signals.py
```

The following files should exist:

```text
data/market_database/daily_price_observations.csv
data/rolling_metrics/rolling_price_metrics.csv
data/market_signals/real_signal_scores.csv
data/market_intelligence/market_intelligence.csv
data/monte_carlo/monte_carlo_summary.csv
```


# MTG Investment Terminal v12

## Main v12 Upgrade: Real-Signal Market Database

v12 keeps the v11 product master, market intelligence, and Monte Carlo layers. It adds a database-first signal engine built around persistent daily market observations and optional real-world signal inputs.

## New Core Files

```text
models/market_database.py
models/real_signal_engine.py
review_real_signals.py
data/market_database/daily_price_observations.csv
data/rolling_metrics/rolling_price_metrics.csv
data/market_signals/real_signal_scores.csv
```

## New Optional Input Templates

```text
data/market_inputs/inventory_signals.csv
data/market_inputs/sales_velocity.csv
data/market_inputs/demand_signals.csv
data/market_inputs/scarcity_signals.csv
```

These let you add real market observations when available.

## Workflow

```text
TCGCSV refresh
↓
Product master approved IDs
↓
Append daily price observations
↓
Calculate rolling price metrics
↓
Merge optional inventory/sales/demand/scarcity inputs
↓
Calculate real_signal_score
↓
Market intelligence + Monte Carlo
↓
Scoring / portfolio recommendation
```

## Run

```bash
python reset_source_cache.py
python run.py
python review_real_signals.py
python review_market_intelligence.py
```

## Important

At first, the real signal engine will mostly use neutral/default values because inventory, sales velocity, demand, and scarcity inputs are blank. As you collect more daily prices and add optional input data, the `real_signal_score` becomes more meaningful.


# MTG Investment Terminal v11

## Main v11 Upgrade: Market Intelligence + Monte Carlo

v11 keeps the v10 product-master and historical investment feature layer, then adds:

- liquidity proxy score
- inventory-risk proxy score
- market regime score
- market intelligence score
- Monte Carlo terminal value simulations
- probability of doubling
- probability of tripling
- probability of loss
- 5th/25th/50th/75th/95th percentile simulated outcomes

## New Files

```text
models/market_intelligence.py
data/market_intelligence/market_intelligence.csv
data/monte_carlo/monte_carlo_summary.csv
review_market_intelligence.py
```

## Run

```bash
python reset_source_cache.py
python run.py
python review_investment_features.py
python review_market_intelligence.py
```

## Important

v11 still starts with limited historical observations. The Monte Carlo uses current assumptions and proxy volatility until enough daily history accumulates. As you run this daily, the history-confidence, volatility, trend, and simulation quality improve.

## Future Data Sources

The liquidity/inventory fields are currently proxy-based. The next improvement would be connecting real:

- listing counts
- seller counts
- sales velocity
- sold listings
- inventory decay
- eBay/Cardmarket comps


# MTG Investment Terminal v10

## Main v10 Upgrade: Historical Investment Database

v10 keeps the v9 product-master system and adds Phase 2 investment intelligence:

- daily historical snapshot tracking
- history-derived metrics
- 30/90/180/365-day return features
- drawdown from historical high
- distance from historical low
- annualized volatility estimate
- momentum score
- drawdown/entry score
- price stability score
- history confidence
- investment feature score

## New Files

```text
models/investment_features.py
data/investment/investment_features.csv
data/investment/historical_metrics.csv
data/investment/investment_model_input.csv
data/reference/release_metadata.csv
review_investment_features.py
```

## How v10 Works

```text
TCGCSV discovery
↓
Product master approved IDs
↓
Current prices
↓
Historical snapshot load
↓
Investment feature calculation
↓
Scoring/projections
↓
Daily snapshot saved
```

## Important

The first run will not have much history yet. That is expected.

The model will start becoming more useful after repeated daily runs because `data/history/price_snapshot_YYYY-MM-DD.csv` accumulates observations.

## Run

```bash
python reset_source_cache.py
python run.py
python review_investment_features.py
```

## Optional Metadata

You can add release MSRP/release dates here:

```text
data/reference/release_metadata.csv
```

Columns:

```text
box_name,release_date,release_msrp,notes
```



# MTG Investment Terminal v9

## Main v9 Upgrade: Product Master Database

v9 stops trusting product-name heuristics as the final authority.

Instead, it creates a permanent **investment product master**:

```text
data/product_master/investment_products.csv
```

Only approved product IDs are scored.

This fixes the recurring problem where TCGCSV product names like `Collector Booster Display` can still refer to a case-level SKU or other wrong product.

## Core v9 Flow

```text
TCGCSV discovery
↓
data/product_master/product_candidates.csv
↓
data/product_master/product_selection_review.csv
↓
data/product_master/investment_products.csv
↓
approved product IDs only
↓
data/product_master/product_master_model_input.csv
↓
scoring/projections/portfolio
```

## Important Files

```text
data/product_master/product_candidates.csv
data/product_master/product_selection_review.csv
data/product_master/investment_products.csv
data/product_master/product_master_model_input.csv
outputs/ranked_boxes.csv
outputs/price_quality_report.csv
```

## Review Product Master

```bash
python review_product_master.py
```

## Manually Approve a Product

```bash
python approve_product.py <tcgcsv_group_id> <tcgplayer_product_id>
```

Example:

```bash
python approve_product.py 23019 484912
```

Then run:

```bash
python reset_source_cache.py
python run.py
```

## Seeded Known Correct Products

v9 starts with approved product IDs for:

- LOTR: `484912`
- FINAL FANTASY: `618893`
- Double Masters 2022: `271509`

Other sets may be marked `review_required` until the product ID is confirmed.

## Why This Matters

A product name alone is not reliable enough. v9 uses persistent product identity so once the correct product ID is approved, the model always uses that ID in future runs.


# v8.1 Hotfix

This package includes the corrected `models/scoring.py` directly. Replace the full project folder or at minimum replace `models/scoring.py`.

Run:

```bash
python reset_source_cache.py
python run.py
```


# MTG Investment Terminal v8

## Main v8 Upgrade: Market Consensus Engine

v8 no longer blindly trusts one TCGCSV price.

It now builds a consensus price from:

- TCGCSV discovered canonical display price
- `data/reference/manual_price_sources.csv`
- future external/manual/eBay/Cardmarket/API sources

The consensus engine:

1. Combines all available source prices by `box_name`
2. Calculates median source price
3. Flags outliers when a source is too far from the median
4. Uses the median of non-outlier sources as `current_price`
5. Writes source-audit files so you can see exactly why a price was chosen

## Why

Some TCGCSV products labeled `Collector Booster Display` appear to be case-level products. For example:

- LOTR TCGCSV canonical display row reported around $5,357
- The individual display market price was around $1,925

v8 can reject that inflated source when a verified/manual source is available.

## Important Files

```text
data/reference/manual_price_sources.csv
data/source_cache/consensus_prices.csv
data/source_cache/all_price_sources.csv
data/discovered/collector_booster_consensus_audit.csv
outputs/price_quality_report.csv
outputs/ranked_boxes.csv
```

## Manual Source File

Add or edit source prices here:

```text
data/reference/manual_price_sources.csv
```

Columns:

```text
box_name
source_name
market_price
low_price
last_price_checked
source_note
source_confidence
```

You can add verified prices from TCGplayer, Cardmarket, eBay sold comps, or your own manually checked source.

## Run

After replacing files:

```bash
python reset_source_cache.py
python run.py
```

Then review:

```text
data/source_cache/consensus_prices.csv
data/source_cache/all_price_sources.csv
```

## Current Manual Overrides Included

v8 includes initial manual-verified/estimated rows for:

- LOTR Collector Booster Display
- Final Fantasy Collector Booster Display
- Double Masters 2022 Collector Booster Display
- Fallout Collector Booster Display placeholder estimate

Update these anytime in `manual_price_sources.csv`.



# v7.1 Case-Price Fix

v7.1 fixes a critical issue where raw TCGCSV products such as **Collector Booster Display Case** could be saved under the same set-level `box_name` as the individual display.

## What changed

- Cases and packs are hard-excluded before canonical selection.
- Only canonical individual Collector Booster Display rows are inserted into the source cache.
- `data/source_cache/latest_prices.csv` is overwritten with canonical display rows only.
- Added `reset_source_cache.py` to clear stale case-level snapshots from older runs.

## Important after upgrading from v7

Run this once:

```bash
python reset_source_cache.py
python run.py
```

Then check:

```text
data/discovered/collector_booster_displays_canonical.csv
outputs/price_quality_report.csv
```

LOTR should use the individual display product, not the display case.



# MTG Investment Terminal v7

## Main v7 Change: Set-Level Canonical Collector Booster Displays

v7 changes the model universe from **product-level rows** to **set-level canonical Collector Booster Display rows**.

The model still discovers all collector booster-related TCGCSV products, but then it selects exactly one canonical product per set/group.

## Why

TCGCSV can return several collector-related products for the same set:

- Collector Booster Display
- Collector Booster Display Case
- Collector Booster Pack
- Japanese Collector Booster Display
- Special variants

For investing, the desired unit is:

```text
Collector Booster Display
```

not cases, packs, samples, bundles, or language variants.

## New Canonical Selection Rules

The selector prefers:

1. `Collector Booster Display`
2. `Collector Booster Box`
3. English/default product
4. Non-case
5. Non-pack
6. Has market price
7. Highest canonical score

It then keeps only one product per `tcgcsv_group_id`.

## New File

```text
models/canonical_products.py
```

## New Audit Output

After discovery, v7 writes:

```text
data/discovered/collector_booster_boxes_discovered.csv
data/discovered/collector_booster_displays_canonical.csv
data/discovered/collector_booster_model_input.csv
```

The first file is the raw discovered universe.
The second file is the canonical display universe.
The third file is what the model scores.

## Target Buy Fix

v7 also fixes target buy logic.

Target buy is now a margin-of-safety price, not projected future value. It should no longer produce impossible outputs like:

```text
Current Price: 1925
Target Buy: 8500
```

The target buy price is capped below current market price unless current/fair-value data is missing.

## Run

```bash
python run.py
```

Then review:

```text
data/discovered/collector_booster_displays_canonical.csv
outputs/ranked_boxes.csv
outputs/price_quality_report.csv
```



# MTG Investment Terminal v6

## Main v6 Fix: Confirm Inputs + Auto-Detect TCGCSV Category

v6 removes the fragile hard-coded category assumption.

Instead of relying on:

```python
TCGCSV_MAGIC_CATEGORY_ID = 1
```

or:

```python
TCGCSV_MAGIC_CATEGORY_ID = 3
```

v6 does this:

```text
/tcgplayer/categories
↓
find category whose name/displayName/seoCategoryName contains Magic
↓
use that categoryId for groups/products/prices
```

This matters because TCGCSV docs show the endpoint structure as:

```text
/tcgplayer/categories
/tcgplayer/{categoryId}/groups
/tcgplayer/{categoryId}/{groupId}/products
/tcgplayer/{categoryId}/{groupId}/prices
```

Products and prices are joined by `productId`.

## Source Request Logging

Every source request is logged here:

```text
data/logs/source_requests.csv
```

If something fails, this file shows:

- timestamp
- source name
- URL
- HTTP status code
- error message

## Useful Commands

Run full model:

```bash
python run.py
```

Debug source category detection:

```bash
python debug_source_layer.py
```

List categories:

```bash
python discover_categories.py
```

Check discovered products:

```bash
python validate_discovery.py
```

## If You Get 401/400 Errors

Open:

```text
data/logs/source_requests.csv
```

That file will show the exact URL, status code, and response message.

## Important Source Notes

TCGCSV is updated once per day and asks users to set a custom User-Agent, limit update frequency, and include a delay between requests. v6 includes those request headers and a configurable delay.



# MTG Investment Terminal v5.1

## Main Upgrade: Automatic Collector Booster Box Discovery

v5.1 no longer requires a manual watchlist.

When you run:

```bash
python run.py
```

the project attempts to:

1. Download all Magic groups from TCGCSV.
2. Download product lists for each group.
3. Filter products to sealed Collector Booster Boxes / Collector Booster Displays.
4. Pull prices for matching products.
5. Write the discovered universe to:

```text
data/discovered/collector_booster_boxes_discovered.csv
data/discovered/collector_booster_model_input.csv
```

6. Auto-create/update:

```text
data/reference/product_map.csv
data/source_cache/latest_prices.csv
data/database/mtg_prices.sqlite
```

7. Score the discovered collector booster box universe.

## Why This Matters

You no longer need to know:

- `tcgcsv_group_id`
- `tcgplayer_product_id`
- exact official product names

The model discovers them from TCGCSV and only keeps products whose names look like sealed collector booster displays/boxes.

## Filtering Logic

Included product names contain terms like:

```text
collector booster display
collector booster box
collector boosters display
collector booster case
```

Excluded product names contain terms like:

```text
pack
sample
blister
bundle
commander deck
draft booster
set booster
play booster
jumpstart
prerelease
```

This is intentionally conservative so the model does not accidentally include single packs or other sealed products.

## Important Output Files

```text
data/discovered/collector_booster_boxes_discovered.csv
data/discovered/collector_booster_model_input.csv
outputs/ranked_boxes.csv
outputs/price_quality_report.csv
outputs/portfolio_recommendation.csv
outputs/projection_audit.csv
```

## Source Notes

TCGCSV exposes categories, groups, products, and prices. Products and prices are joined by `productId`. The model uses this structure to discover collector booster boxes automatically.

## One Setup Check

The config currently uses:

```python
TCGCSV_MAGIC_CATEGORY_ID = 1
```

If discovery returns the wrong game or zero Magic products, run:

```bash
python discover_categories.py
```

then update `TCGCSV_MAGIC_CATEGORY_ID` in `config.py` to the Magic: The Gathering category ID shown by TCGCSV.



# MTG Investment Terminal v5

## Main Upgrade: Source Layer + SQLite Price History

v5 adds a real source-data layer. The model now supports:

1. **TCGCSV** public pricing files for sealed product market prices.
2. **TCGplayer API** optional pricing connector if you already have API credentials.
3. **MTGJSON** set metadata enrichment.
4. **Scryfall** chase-card summary enrichment.

## Important Note About TCGplayer API Access

TCGplayer documentation says new API access is no longer being granted. Because of that, v5 treats the TCGplayer API as optional. If you already have credentials, set:

```bash
set TCGPLAYER_ACCESS_TOKEN=your_token_here
```

and set this in `config.py`:

```python
USE_TCGPLAYER_API = True
```

Otherwise, use TCGCSV as the main price source.

## New Run Flow

```text
python run.py
↓
update_prices.py
↓
collectors/
  tcgcsv_collector.py
  tcgplayer_api_collector.py
  mtgjson_collector.py
  scryfall_collector.py
↓
data/database/mtg_prices.sqlite
↓
data/source_cache/latest_prices.csv
↓
scoring/projections/portfolio optimizer
```

## New Database

```text
data/database/mtg_prices.sqlite
```

Tables:

```text
product_mapping
price_snapshots
source_runs
```

## Product Mapping

The key file is:

```text
data/reference/product_map.csv
```

For TCGCSV automated sealed-box pricing, each product needs:

```text
box_name
tcgplayer_product_id
tcgcsv_category_id
tcgcsv_group_id
```

`tcgcsv_category_id` is typically `3` for Magic, but `tcgcsv_group_id` must be filled for each set/product group.

## Source Health

Run:

```bash
python source_health.py
```

This shows:

- latest source cache
- recent source runs
- latest database price snapshots

## Current Practical Setup

The project includes verified manual prices for LOTR, Final Fantasy, and Double Masters 2022. TCGCSV automation is ready, but you still need to fill `tcgcsv_group_id` values in `product_map.csv` before TCGCSV can pull those exact group price files.



# MTG Investment Terminal v4

## Main Upgrade: Source Data Layer

v4 stops treating the watchlist CSV as the pricing source of truth.

When you run:

```bash
python run.py
```

the model now:

1. Loads your watchlist from `data/input/collector_booster_boxes.csv`
2. Loads product mapping from `data/reference/product_map.csv`
3. Loads latest prices from `data/source_cache/latest_prices.csv`
4. Updates `current_price` from `market_price`
5. Calculates `price_data_quality`
6. Flags prices as `OK`, `STALE`, `LOW_QUALITY`, or `MISSING`
7. Writes `outputs/price_quality_report.csv`
8. Scores and projects using refreshed prices

## Important Files

```text
data/input/collector_booster_boxes.csv      # watchlist and manual model factors
data/reference/product_map.csv              # product IDs and verified product mapping
data/source_cache/latest_prices.csv         # latest price source cache
outputs/price_quality_report.csv            # source-data audit output
```

## Current Source Behavior

v4 does not scrape websites. It uses a source-cache architecture.

That means you can update `latest_prices.csv` manually today, and later a TCGCSV or TCGplayer API collector can write into the same file automatically.

## New Price Fields

```text
tcgplayer_product_id
price_source
market_price
low_price
last_price_checked
price_data_quality
price_status
```

## Corrected Seed Prices Included

The source cache includes corrected manual-verified prices for:

- The Lord of the Rings Collector Booster Box: 1925
- Final Fantasy Collector Booster Box: 1525
- Double Masters 2022 Collector Booster Box: 405

## Projection Upgrade

v4 also includes tiered CAGR caps so strong boxes do not all hit the same exact projection ceiling.


# MTG Investment Terminal

A data-driven Magic: The Gathering sealed collector booster box investment model.

This project is built to evolve from a local CSV model into a full sealed-product investment terminal with:

- multi-factor investment scoring
- bear/base/bull projection cases
- projection confidence
- daily price snapshots
- portfolio optimization
- projection audit files
- Streamlit dashboard shell
- hooks for TCGCSV, MTGJSON, Scryfall, and future eBay sold comps

## Quick Start

```bash
pip install -r requirements.txt
python run.py
```

Optional dashboard:

```bash
streamlit run dashboard/streamlit_app.py
```

## Main Outputs

After running `python run.py`, check:

```text
outputs/ranked_boxes.csv
outputs/portfolio_recommendation.csv
outputs/projection_audit.csv
outputs/market_summary.csv
data/history/price_snapshot_YYYY-MM-DD.csv
```

## Input File

Edit:

```text
data/input/collector_booster_boxes.csv
```

Each row represents one sealed collector booster box.

The model is intentionally designed so you can start manually, then later replace manual fields with live source pulls.

## Philosophy

This model does not try to predict exact future prices. It ranks sealed products using repeatable investment logic:

1. Prefer strong demand, IP, chase-card depth, and long-term collectibility.
2. Penalize supply-dump risk, reprint risk, liquidity risk, and overly concentrated chase value.
3. Use cohort-like assumptions to estimate likely 5-year return ranges.
4. Separate ranking score from projection confidence.
5. Recommend portfolios only from products that clear quality filters.


## Version 3.2 Updates

This version adjusts the model based on the first terminal run:

- Portfolio quality threshold changed from `78` to `74`
- Base CAGR cap changed from `30%` to `24%`
- Bull CAGR cap changed from `38%` to `32%`

Why:

- The v3.1 portfolio filter was too strict and only selected LOTR.
- The previous projection cap allowed elite boxes to project too aggressively.
- v3.2 should allow high-quality boxes like Double Masters 2022, Kamigawa Neon Dynasty, and Final Fantasy back into the portfolio while still excluding weaker speculative boxes.
