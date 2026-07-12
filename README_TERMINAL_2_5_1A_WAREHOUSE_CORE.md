# Terminal 2.5.1a — Warehouse Core

Additive centralized warehouse foundation.

## Run

```bat
python terminal2_warehouse_init.py
python terminal2_warehouse_validate.py
python -m pytest tests/test_warehouse_core.py
```

Generated files under `data/warehouse/` remain local and ignored by Git. Existing Terminal 2 exports are unchanged.
