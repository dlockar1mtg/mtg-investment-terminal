from terminal2.warehouse_core import DashboardPublisher,Warehouse
from .contracts import get_archive_contract
from .engine import build_secret_lair_archive
def publish_archive_datasets(ds,warehouse=None):return DashboardPublisher(warehouse or Warehouse()).publish_many([(f,get_archive_contract(n).definition()) for n,f in ds.items()],message='Terminal 2.10.0 Secret Lair historical market archive')
def publish_secret_lair_archive(warehouse=None):
 r=build_secret_lair_archive();p=publish_archive_datasets(r.datasets,warehouse);s=r.datasets['secret_lair_archive_summary'].iloc[0];return {'datasets':len(p),'observations':int(s['archive_observation_count']),'covered_products':int(s['covered_product_count']),'historical_ready':int(s['historical_ready_count']),'apply_ready':bool(s['apply_ready'])}
