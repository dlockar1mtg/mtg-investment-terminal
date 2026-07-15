import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from terminal2.secret_lair.master_database import engine
class Fake:
 pass
class T(unittest.TestCase):
 def test_builds_products_and_prices(self):
  official=pd.DataFrame([{"source_name":"official_secret_lair","source_record_id":"o1","source_product_name":"Secret Lair: Cats Foil Edition","source_url":"https://official/cats","group_name":"","published_on":"2024-01-01","market_price":None,"low_price":None,"tcgplayer_product_id":"","tcgcsv_group_id":"","tcgcsv_category_id":"","raw_json":""}])
  tcg=pd.DataFrame([{"source_name":"tcgcsv","source_record_id":"100","source_product_name":"Secret Lair: Cats Foil Edition","source_url":"https://tcg/100","group_name":"Secret Lair","published_on":"2024-01-01","market_price":75.0,"low_price":65.0,"tcgplayer_product_id":"100","tcgcsv_group_id":"10","tcgcsv_category_id":"1","raw_json":""}])
  cards=pd.DataFrame(columns=["scryfall_id","card_name","released_at","artist","collector_number","finishes","tcgplayer_id"])
  with tempfile.TemporaryDirectory() as d,patch.object(engine,"MASTER_ROOT",Path(d)),patch.object(engine,"MASTER_PRODUCTS_PATH",Path(d)/"products.csv"),patch.object(engine,"MASTER_HISTORY_PATH",Path(d)/"history.csv"),patch.object(engine,"PRODUCT_MAP_PATH",Path(d)/"map.csv"),patch.object(engine,"official_records",return_value=official),patch.object(engine,"tcgcsv_records",return_value=tcg),patch.object(engine,"scryfall_cards",return_value=cards):
   r=engine.build_master_secret_lair_database(client=Fake())
  self.assertEqual(len(r.datasets),8);self.assertEqual(len(r.datasets["master_secret_lair_products"]),1);self.assertEqual(len(r.datasets["master_secret_lair_prices_current"]),1);self.assertEqual(r.datasets["master_secret_lair_products"].iloc[0]["finish"],"foil")
if __name__=="__main__":unittest.main()
