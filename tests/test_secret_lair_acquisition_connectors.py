from pathlib import Path
import tempfile,unittest,json
import pandas as pd
from terminal2.secret_lair.acquisition.connectors import CsvConnector,JsonConnector,DirectoryConnector
class Tests(unittest.TestCase):
 def test_csv(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a.csv'; pd.DataFrame([{'record_type':'catalog','name':'A'},{'record_type':'price','name':'B'}]).to_csv(p,index=False)
   r=CsvConnector().load(p); self.assertEqual(len(r.catalog),1); self.assertEqual(len(r.prices),1)
 def test_json(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a.json'; p.write_text(json.dumps({'catalog':[{'x':1}],'prices':[{'x':2}]}))
   r=JsonConnector().load(p); self.assertEqual(r.raw_rows,2)
if __name__=='__main__': unittest.main()
