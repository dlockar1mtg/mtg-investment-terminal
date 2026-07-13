# Terminal 2.5.4 — Portfolio Intelligence Engine

This release adds actual-holdings analytics and a model allocation for users
who have not yet entered positions.

## Set up holdings

```bat
python terminal2_create_portfolio_template.py
copy data\terminal2\portfolio_holdings_template.csv data\terminal2\portfolio_holdings.csv
```

Edit `portfolio_holdings.csv` using approved `investment_product_id` values.
The personal holdings file is ignored by Git.

## Publish and validate

```bat
python terminal2_publish_portfolio_intelligence.py --capital 10000 --positions 12
python terminal2_portfolio_warehouse_validate.py
```

Seven standardized datasets publish to the warehouse, including positions,
allocation, risk exposure, recommendations, candidate allocation, scenarios,
and an executive portfolio summary.
