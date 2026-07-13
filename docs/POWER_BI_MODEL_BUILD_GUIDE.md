# Power BI Model Build Guide

1. Use **Get Data → Folder** and select
   `data/warehouse/current/semantic/`, or connect to each semantic CSV.
2. Keep the eleven semantic table names unchanged.
3. Apply the relationships listed in `semantic_relationship_map`.
4. Mark `semantic_dim_date[Date]` as the model date table.
5. Sort `MonthName` by `MonthNumber` and `YearMonth` by `YearMonthSort`.
6. Hide technical keys from report view after relationships are created.
7. Create the measures listed in `semantic_measure_catalog`.
8. Use `semantic_executive_kpis` for contract-driven KPI cards and
   `semantic_refresh_status` for an administration page.
9. Do not relate fact tables directly to each other.
10. Refresh Terminal 2 before refreshing Power BI.
