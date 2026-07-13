# Terminal 2.5.6 — Power BI Semantic Layer

This release publishes a curated star-schema layer under:

```text
data/warehouse/current/semantic/
```

## Publish and validate

```bat
python terminal2_publish_semantic_layer.py
python terminal2_semantic_layer_validate.py
```

Power BI should connect to the semantic folder rather than the full technical
warehouse. Use `semantic_relationship_map.csv` to create model relationships
and `semantic_measure_catalog.csv` as the starting DAX measure specification.
