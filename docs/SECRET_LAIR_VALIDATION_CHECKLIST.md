# Secret Lair Validation Checklist

Before importing:

- One row per investable variant and finish
- Drop name and variant name are populated
- Finish uses an approved value
- MSRP reflects the original sale price
- Release and sale-window dates use YYYY-MM-DD
- Multiple artists are separated with `|`
- Franchise and IP classification are explicit
- Source name and source record ID are retained when available

After importing:

```bat
python terminal2_publish_secret_lair_registry.py
python terminal2_secret_lair_validate.py
```

Resolve all error findings before starting pricing work. Warnings may remain
when historical metadata is genuinely unavailable, but they should be reviewed.
