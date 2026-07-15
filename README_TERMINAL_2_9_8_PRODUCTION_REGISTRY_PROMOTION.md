# Terminal 2.9.8 — Production Registry Promotion

This release promotes vetted Master Secret Lair Database products and real
price observations into the production registry through an explicit,
backup-protected command.

Preview:

```bat
python terminal2_promote_secret_lair_production.py
```

Apply after reviewing the seven promotion datasets:

```bat
python terminal2_promote_secret_lair_production.py --apply
```

The full pipeline publishes promotion status but never applies a promotion.
