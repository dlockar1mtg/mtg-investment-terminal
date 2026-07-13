# Terminal 2.5.2 — Market Intelligence Standardization

Module 2 market datasets now publish directly through the Dashboard Publisher
using formal dataset contracts.

## Validate

```bat
python -m unittest tests.test_market_contracts -v
python -m unittest tests.test_market_publication -v
python terminal2_module2_run_all.py
python terminal2_market_warehouse_validate.py
```

Legacy dashboard CSVs remain available. Canonical market datasets are under
`data/warehouse/current/`.
