# Secret Lair Promotion Operations

1. Build and validate the Master Secret Lair Database.
2. Run promotion preview.
3. Review candidates, rejections, prices, and remaining review rows.
4. Apply with `--apply`.
5. Publish registry, pricing, population, and intelligence.
6. Validate all downstream layers.
7. Restore timestamped backups from
   `data/terminal2/secret_lair_promotion/backups/` if rollback is required.

Use `--replace` only when intentionally rebuilding production from the eligible
Master Database universe. Default apply merges and deduplicates.
