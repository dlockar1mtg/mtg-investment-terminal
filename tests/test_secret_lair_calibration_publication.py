from pathlib import Path
import tempfile,unittest,pandas as pd
from terminal2.secret_lair.calibration.contracts import CALIBRATION_CONTRACTS
from terminal2.secret_lair.calibration.exports import publish_calibration_datasets
from terminal2.warehouse_core import Warehouse,get_warehouse_config
class T(unittest.TestCase):
 def test_publish(self):
  ds={n:pd.DataFrame(columns=c.required_columns) for n,c in CALIBRATION_CONTRACTS.items()}
  ds["secret_lair_calibration_summary"]=pd.DataFrame([{"snapshot_date":"2026-07-14","product_count":0,"priced_count":0,"historical_count":0,"current_price_only_count":0,"insufficient_count":0,"provisional_watch_count":0,"provisional_hold_count":0,"actionable_buy_count":0,"score_spread":0,"calibration_status":"EMPTY"}])
  with tempfile.TemporaryDirectory() as d:
   p=publish_calibration_datasets(ds,Warehouse(config=get_warehouse_config(Path(d))))
   self.assertEqual(len(p),5)
if __name__=="__main__":unittest.main()
