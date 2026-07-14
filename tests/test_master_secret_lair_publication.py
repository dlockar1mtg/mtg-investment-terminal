from pathlib import Path
import tempfile,unittest,pandas as pd
from terminal2.secret_lair.master_database.contracts import MASTER_DATABASE_CONTRACTS
from terminal2.secret_lair.master_database.exports import publish_master_database_datasets
from terminal2.warehouse_core import Warehouse,get_warehouse_config
class T(unittest.TestCase):
 def test_publish(self):
  ds={n:pd.DataFrame(columns=c.required_columns) for n,c in MASTER_DATABASE_CONTRACTS.items()};ds["master_secret_lair_summary"]=pd.DataFrame([{"snapshot_date":"2026-07-14","source_product_count":0,"canonical_product_count":0,"current_price_count":0,"historical_observation_count":0,"review_count":0,"registry_ready_count":0}])
  with tempfile.TemporaryDirectory() as d:self.assertEqual(len(publish_master_database_datasets(ds,Warehouse(config=get_warehouse_config(Path(d))))),8)
if __name__=="__main__":unittest.main()
