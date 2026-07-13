# Terminal 2.5.3 — Historical Intelligence Standardization

Historical price observations, monthly history, returns, price features,
coverage, source quality, and the executive historical summary now publish
directly through the Dashboard Publisher.

## Validate

```bat
python -m unittest tests.test_historical_contracts -v
python -m unittest tests.test_historical_publication -v
python terminal2_publish_historical_intelligence.py
python terminal2_historical_warehouse_validate.py
```

Canonical current datasets are under `data/warehouse/current/`, while each
publication also produces an immutable snapshot under `data/warehouse/history/`.
