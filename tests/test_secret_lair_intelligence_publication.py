from pathlib import Path
import tempfile,unittest,pandas as pd
from terminal2.secret_lair.intelligence_expansion.contracts import EXPANSION_CONTRACTS
from terminal2.secret_lair.intelligence_expansion.exports import publish_expansion_datasets
from terminal2.warehouse_core import Warehouse,get_warehouse_config
class T(unittest.TestCase):
 def test_publish(self):
  ds={n:pd.DataFrame(columns=c.required_columns) for n,c in EXPANSION_CONTRACTS.items()};ds['secret_lair_intelligence_summary']=pd.DataFrame([{'snapshot_date':'2026-07-14','asset_count':0,'priced_asset_count':0,'actionable_count':0,'average_score':pd.NA,'average_confidence':pd.NA,'average_risk':pd.NA}])
  with tempfile.TemporaryDirectory() as d:self.assertEqual(len(publish_expansion_datasets(ds,Warehouse(config=get_warehouse_config(Path(d))))),14)
if __name__=='__main__':unittest.main()
