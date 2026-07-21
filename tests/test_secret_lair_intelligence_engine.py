from pathlib import Path
import tempfile,unittest,pandas as pd
from terminal2.secret_lair.intelligence_expansion.engine import build_secret_lair_intelligence_expansion
class T(unittest.TestCase):
 def test_empty_safe(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d)/'r.csv';p=Path(d)/'p.csv';pd.DataFrame(columns=['secret_lair_id','drop_name','variant_name','finish','product_family','release_date','sale_start_date','sale_end_date','msrp_usd','currency','franchise','ip_category','universes_beyond','artist_names','card_count','superdrop_name','event_type','availability_model','status','official_url','source_name','source_record_id','notes']).to_csv(r,index=False);pd.DataFrame(columns=['observation_date','secret_lair_id','source_name','market_price','low_price','listing_count','sales_count_30d','currency','source_url','source_record_id','price_data_quality','notes']).to_csv(p,index=False);x=build_secret_lair_intelligence_expansion(r,p);self.assertGreaterEqual(len(x.datasets),14);self.assertTrue(x.datasets['secret_lair_investment_universe'].empty)
if __name__=='__main__':unittest.main()
