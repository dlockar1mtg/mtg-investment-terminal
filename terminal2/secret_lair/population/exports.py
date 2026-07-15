from terminal2.warehouse_core import DashboardPublisher,Warehouse
from .contracts import get_population_contract
from .engine import build_secret_lair_population
def publish_population_datasets(datasets,warehouse=None):return DashboardPublisher(warehouse or Warehouse()).publish_many([(df,get_population_contract(n).definition()) for n,df in datasets.items()],message="Terminal 2.9.6 Secret Lair data population")
def publish_secret_lair_population(warehouse=None):
 r=build_secret_lair_population();publish_population_datasets(r.datasets,warehouse);s=r.datasets["secret_lair_population_summary"].iloc[0];return {"datasets":len(r.datasets),"catalog_rows":int(s["catalog_rows"]),"accepted_rows":int(s["accepted_rows"]),"review_rows":int(s["review_rows"]),"registry_assets":int(s["registry_assets"]),"priced_assets":int(s["priced_assets"]),"scoring_ready_assets":int(s["scoring_ready_assets"]),"apply_ready":bool(s["apply_ready"])}
