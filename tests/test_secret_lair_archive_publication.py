from pathlib import Path
import tempfile,unittest,pandas as pd
from terminal2.secret_lair.archive.contracts import ARCHIVE_CONTRACTS
from terminal2.secret_lair.archive.exports import publish_archive_datasets
from terminal2.warehouse_core import Warehouse,get_warehouse_config
class T(unittest.TestCase):
 def test_publish(self):
  ds={n:pd.DataFrame(columns=c.required_columns) for n,c in ARCHIVE_CONTRACTS.items()}
  with tempfile.TemporaryDirectory() as d:self.assertEqual(len(publish_archive_datasets(ds,Warehouse(config=get_warehouse_config(Path(d))))),9)
if __name__=='__main__':unittest.main()
