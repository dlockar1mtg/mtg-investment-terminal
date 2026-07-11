# v5.1 Changelog

## Added
- Automatic TCGCSV collector booster box discovery.
- `collectors/tcgcsv_discovery.py`
- `discover_categories.py`
- `validate_discovery.py`
- `data/discovered/collector_booster_boxes_discovered.csv`
- `data/discovered/collector_booster_model_input.csv`

## Changed
- `run.py` now uses the discovered model input file when discovery mode is enabled.
- `update_prices.py` discovers products before scoring.
- `product_map.csv` can now be generated automatically from discovered products.

## Important
If TCGCSV's Magic category ID differs in your environment, run:

```bash
python discover_categories.py
```

Then update:

```python
TCGCSV_MAGIC_CATEGORY_ID = <correct id>
```
