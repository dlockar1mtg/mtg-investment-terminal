from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
import pandas as pd
from terminal2.secret_lair.master_database import registry_export
class T(unittest.TestCase):
 def test_exports_only_confident_products(self):
  products=pd.DataFrame([{"secret_lair_id":"SL-1","drop_name":"Cats","variant_name":"Foil Edition","finish":"foil","product_family":"drop","source_confidence":90}])
  prices=pd.DataFrame([{"observation_date":"2026-07-14","secret_lair_id":"SL-1","source_name":"tcgcsv","market_price":75,"low_price":65,"source_record_id":"100"}])
  with tempfile.TemporaryDirectory() as d,patch.object(registry_export,"MASTER_ROOT",Path(d)),patch.object(registry_export,"PROPOSED_REGISTRY_PATH",Path(d)/"registry.csv"),patch.object(registry_export,"PROPOSED_PRICES_PATH",Path(d)/"prices.csv"):
   out=registry_export.export_master_database_import_files({"master_secret_lair_products":products,"master_secret_lair_prices_current":prices})
  self.assertEqual(out["registry_rows"],1);self.assertEqual(out["price_rows"],1)
if __name__=="__main__":unittest.main()
