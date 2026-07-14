from pathlib import Path
import tempfile,unittest,pandas as pd
from terminal2.secret_lair.discovery.contracts import DISCOVERY_CONTRACTS
from terminal2.secret_lair.discovery.exports import publish_discovery_datasets
from terminal2.warehouse_core import Warehouse,get_warehouse_config
class Tests(unittest.TestCase):
 def test_empty(self):
  data={n:pd.DataFrame(columns=c.required_columns) for n,c in DISCOVERY_CONTRACTS.items()}
  with tempfile.TemporaryDirectory() as temp:self.assertEqual(len(publish_discovery_datasets(data,Warehouse(config=get_warehouse_config(Path(temp))))),7)
if __name__=='__main__':unittest.main()
