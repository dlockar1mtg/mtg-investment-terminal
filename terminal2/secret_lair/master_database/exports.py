from terminal2.warehouse_core import DashboardPublisher,Warehouse
from .contracts import get_master_database_contract
from .engine import build_master_secret_lair_database

def publish_master_database_datasets(datasets,warehouse=None):
 pub=DashboardPublisher(warehouse or Warehouse());return pub.publish_many([(df,get_master_database_contract(n).definition()) for n,df in datasets.items()],message="Terminal 2.9.7 Master Secret Lair Database")
def publish_master_secret_lair_database(*,refresh=False,max_tcgcsv_groups=None,warehouse=None):
 result=build_master_secret_lair_database(refresh=refresh,max_tcgcsv_groups=max_tcgcsv_groups);published=publish_master_database_datasets(result.datasets,warehouse);s=result.datasets["master_secret_lair_summary"].iloc[0]
 return {"datasets":len(published),"source_products":int(s["source_product_count"]),"canonical_products":int(s["canonical_product_count"]),"current_prices":int(s["current_price_count"]),"history_rows":int(s["historical_observation_count"]),"review_rows":int(s["review_count"]),"registry_ready":int(s["registry_ready_count"]),"local_root":result.local_root}
