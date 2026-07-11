# v9 Changelog

## Added
- Product master workflow.
- `models/product_master.py`
- `review_product_master.py`
- `approve_product.py`
- `data/product_master/investment_products.csv`
- `data/product_master/product_candidates.csv`
- `data/product_master/product_selection_review.csv`
- `data/product_master/product_master_model_input.csv`

## Changed
- The model now scores approved product IDs only.
- Name-based canonicalization is no longer the final authority.
- TCGCSV discovery writes candidate products for review instead of blindly choosing the scoring universe.

## Seeded
- LOTR product ID 484912
- Final Fantasy product ID 618893
- Double Masters 2022 product ID 271509
