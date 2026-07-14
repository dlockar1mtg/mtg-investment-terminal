from terminal2.secret_lair.discovery.contracts import get_discovery_contract
from terminal2.secret_lair.discovery.engine import discover_secret_lairs
from terminal2.warehouse_core import DashboardPublisher,Warehouse
def publish_discovery_datasets(datasets,warehouse=None):return DashboardPublisher(warehouse or Warehouse()).publish_many([(df,get_discovery_contract(n).definition()) for n,df in datasets.items()],message='Terminal 2.7.1 Secret Lair discovery')
def publish_secret_lair_discovery(warehouse=None):
    r=discover_secret_lairs(); p=publish_discovery_datasets(r.datasets,warehouse); s=r.datasets['secret_lair_discovery_summary'].iloc[0]
    return {'datasets':len(p),'config_exists':r.config_exists,'enabled_sources':int(s['enabled_sources']),'successful_sources':int(s['successful_sources']),'discovered_rows':int(s['discovered_rows']),'new_candidate_rows':int(s['new_candidate_rows']),'review_candidate_rows':int(s['review_candidate_rows']),'known_rows':int(s['known_rows']),'conflict_rows':int(s['conflict_rows']),'stage_ready':bool(s['acquisition_stage_ready'])}
