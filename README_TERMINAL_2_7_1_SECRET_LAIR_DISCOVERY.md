# Terminal 2.7.1 — Automated Secret Lair Discovery

Adds incremental discovery with cache-aware HTTP and local connectors, raw snapshots, official-store HTML parsing, normalized JSON, Scryfall and MTGJSON metadata parsing, known/new classification, conflicts, source health, and optional acquisition staging.

```bat
python terminal2_create_secret_lair_discovery_template.py
python terminal2_run_secret_lair_discovery.py
python terminal2_secret_lair_discovery_validate.py
```

Use `--stage-acquisition` only after reviewing candidates. Discovery never modifies the registry.
