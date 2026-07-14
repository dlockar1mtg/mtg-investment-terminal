from __future__ import annotations
from .contracts import get_acquisition_contract
from .engine import acquire_secret_lair_sources
from terminal2.warehouse_core import DashboardPublisher, Warehouse

def publish_acquisition_datasets(datasets, warehouse: Warehouse|None=None):
    publisher=DashboardPublisher(warehouse or Warehouse())
    return publisher.publish_many([(df,get_acquisition_contract(name).definition()) for name,df in datasets.items()],message="Terminal 2.7.0 Secret Lair source acquisition")

def publish_secret_lair_acquisition(warehouse: Warehouse|None=None) -> dict:
    result=acquire_secret_lair_sources(); published=publish_acquisition_datasets(result.datasets,warehouse)
    summary=result.datasets["secret_lair_acquisition_summary"].iloc[0]
    return {"datasets":len(published),"source_config_exists":result.source_config_exists,"enabled_sources":int(summary["enabled_sources"]),"successful_sources":int(summary["successful_sources"]),"catalog_rows":int(summary["catalog_rows"]),"price_rows":int(summary["price_rows"]),"conflict_rows":int(summary["conflict_rows"]),"backfill_ready":bool(summary["backfill_ready"])}
