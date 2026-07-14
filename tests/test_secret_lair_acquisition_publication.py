from pathlib import Path
import tempfile,unittest
import pandas as pd
from terminal2.secret_lair.acquisition.engine import acquire_secret_lair_sources
from terminal2.secret_lair.acquisition.exports import publish_acquisition_datasets
from terminal2.warehouse_core import Warehouse,get_warehouse_config
class Tests(unittest.TestCase):
 def test_empty_publish(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); config=root/'config.csv'; pd.DataFrame(columns=['source_name','connector_type','location','enabled','priority','source_quality','default_currency','catalog_mapping_json','price_mapping_json','notes']).to_csv(config,index=False)
   ds=acquire_secret_lair_sources(config).datasets; pub=publish_acquisition_datasets(ds,Warehouse(config=get_warehouse_config(root))); self.assertEqual(len(pub),7)
if __name__=='__main__': unittest.main()
