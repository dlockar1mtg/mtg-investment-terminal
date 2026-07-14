from terminal2.warehouse_core import DashboardPublisher,Warehouse
from .contracts import get_expansion_contract
from .engine import build_secret_lair_intelligence_expansion
def publish_expansion_datasets(datasets,warehouse=None):return DashboardPublisher(warehouse or Warehouse()).publish_many([(df,get_expansion_contract(n).definition()) for n,df in datasets.items()],message='Terminal 2.9.5 Secret Lair intelligence expansion')
def publish_secret_lair_intelligence_expansion(warehouse=None):
 r=build_secret_lair_intelligence_expansion();p=publish_expansion_datasets(r.datasets,warehouse);s=r.datasets['secret_lair_intelligence_summary'].iloc[0];return {'datasets':len(p),'secret_lair_assets':int(s['asset_count']),'priced_secret_lairs':int(s['priced_asset_count']),'actionable_secret_lairs':int(s['actionable_count']),'unified_products':len(r.datasets['unified_investment_products'])}
