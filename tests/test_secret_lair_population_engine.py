import unittest
from unittest.mock import patch
import pandas as pd
from terminal2.secret_lair.population import engine
class R: 
 def __init__(self,d):self.datasets=d
class T(unittest.TestCase):
 def test_empty_safe(self):
  back={"secret_lair_match_results":pd.DataFrame(columns=['source_name','source_record_id','match_status']),"secret_lair_unmatched_review":pd.DataFrame(),"secret_lair_backfill_registry":pd.DataFrame(columns=['secret_lair_id','drop_name','variant_name']),"secret_lair_backfill_coverage":pd.DataFrame()}
  pricing={"secret_lair_price_observations":pd.DataFrame()}
  with patch.object(engine,'build_secret_lair_backfill',return_value=R(back)),patch.object(engine,'build_secret_lair_pricing_datasets',return_value=R(pricing)):
   r=engine.build_secret_lair_population();self.assertEqual(len(r.datasets),7);self.assertEqual(r.datasets['secret_lair_population_summary'].iloc[0]['catalog_rows'],0)
if __name__=='__main__':unittest.main()
