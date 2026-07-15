from pathlib import Path
import tempfile,unittest,pandas as pd
from terminal2.secret_lair.population.contracts import POPULATION_CONTRACTS
from terminal2.secret_lair.population.exports import publish_population_datasets
from terminal2.warehouse_core import Warehouse,get_warehouse_config
class T(unittest.TestCase):
 def test_publish(self):
  ds={n:pd.DataFrame(columns=c.required_columns) for n,c in POPULATION_CONTRACTS.items()};ds['secret_lair_population_summary']=pd.DataFrame([{'snapshot_date':'2026-07-14','catalog_rows':0,'accepted_rows':0,'review_rows':0,'duplicate_rows':0,'conflict_rows':0,'registry_assets':0,'priced_assets':0,'scoring_ready_assets':0,'forecast_ready_assets':0,'calibration_ready_assets':0,'apply_ready':False}])
  with tempfile.TemporaryDirectory() as d:self.assertEqual(len(publish_population_datasets(ds,Warehouse(config=get_warehouse_config(Path(d))))),7)
if __name__=='__main__':unittest.main()
