# Terminal 2.5.1c — Warehouse Migration

```bat
python terminal2_migrate_dashboard_warehouse.py
python terminal2_warehouse_migration_validate.py
python -m unittest tests.test_warehouse_migration -v
python -m unittest tests.test_developer_export_source -v
```

Canonical Power BI datasets are written under
`data/warehouse/current/`. Legacy outputs are preserved.
