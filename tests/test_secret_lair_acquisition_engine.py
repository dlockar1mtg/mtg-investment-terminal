from pathlib import Path
import tempfile,unittest,json
import pandas as pd
from terminal2.secret_lair.acquisition.engine import acquire_secret_lair_sources
class Tests(unittest.TestCase):
 def test_csv_acquisition(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); source=root/'source.csv'; config=root/'config.csv'
   pd.DataFrame([{'record_type':'catalog','id':'1','name':'Example','variant':'Foil','finish':'foil'}]).to_csv(source,index=False)
   mapping=json.dumps({'source_record_id':'id','drop_name':'name','variant_name':'variant','finish':'finish'})
   pd.DataFrame([{'source_name':'demo','connector_type':'csv','location':str(source),'enabled':'true','priority':'1','source_quality':'90','default_currency':'USD','catalog_mapping_json':mapping,'price_mapping_json':'{}'}]).to_csv(config,index=False)
   r=acquire_secret_lair_sources(config); self.assertEqual(len(r.datasets['secret_lair_acquisition_catalog']),1); self.assertEqual(len(r.datasets['secret_lair_acquisition_conflicts']),0)
if __name__=='__main__': unittest.main()
