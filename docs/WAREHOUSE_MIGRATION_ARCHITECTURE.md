# Terminal 2.5.1c — Warehouse Migration Architecture

Existing CSVs under `data/dashboard/` and `data/analytics/current/`
are discovered and republished through the Dashboard Publisher into
`data/warehouse/current/`.

Legacy files remain untouched for compatibility. Migration reporting is
written to `data/warehouse/manifests/`.
