# Terminal 2.7.0 — Secret Lair Source Acquisition & Catalog Population

This release adds configurable local CSV, JSON, and directory connectors. It
normalizes external source records into the existing 2.6.2 backfill contracts.

Create the configuration template:

```bat
python terminal2_create_secret_lair_acquisition_template.py
```

Run and validate:

```bat
python terminal2_run_secret_lair_acquisition.py
python terminal2_secret_lair_acquisition_validate.py
```

The release does not silently scrape websites. Acquisition sources are explicit,
auditable, and locally configured. Acquired rows are published for review before
the guarded 2.6.2 backfill apply workflow is used.
