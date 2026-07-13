# Terminal 2.6.0 — Secret Lair Data Foundation

This release creates a curated, versioned Secret Lair registry subsystem.

## Start the local registry

```bat
python terminal2_create_secret_lair_template.py
```

This creates:

```text
data/terminal2/secret_lair_registry.csv
```

The local registry is ignored by Git.

## Import a completed CSV

```bat
python terminal2_import_secret_lair_registry.py path\to\completed_registry.csv
```

## Publish and validate

```bat
python terminal2_publish_secret_lair_registry.py
python terminal2_secret_lair_validate.py
```

An empty registry is valid but produces a warning. No pricing or forecast claims
are made until curated assets are loaded.
