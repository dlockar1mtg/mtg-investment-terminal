# Secret Lair Acquisition Configuration Guide

Each row in `secret_lair_acquisition_sources.csv` defines one source. `location`
may be absolute or project-relative. Mapping JSON uses canonical field names as
keys and source column names as values, for example:

```json
{"source_record_id":"product_id","drop_name":"title","variant_name":"edition","finish":"finish"}
```

Keep disabled sources in the file for documentation. A failed enabled connector
causes validation to fail; a disabled connector does not.
