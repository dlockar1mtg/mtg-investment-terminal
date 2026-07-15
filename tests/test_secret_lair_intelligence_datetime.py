import unittest
import pandas as pd
from terminal2.secret_lair.intelligence_expansion.engine import _features

class SecretLairIntelligenceDatetimeTests(unittest.TestCase):
    def test_features_accept_mixed_timezone_dates(self):
        universe=pd.DataFrame([{
            'investment_product_id':'SL-1','asset_class':'Secret Lair',
            'product_name':'Test — Foil','secret_lair_id':'1','drop_name':'Test',
            'variant_name':'Foil','finish':'foil','release_date':'2021-03-01T08:00:00Z',
            'sale_start_date':'2021-02-01','sale_end_date':'2021-02-28T23:59:59Z',
            'msrp_usd':39.99,'current_price':100.0,'franchise':'Magic',
            'universes_beyond':False,'artist_names':'Artist','card_count':5,
            'availability_model':'time-boxed'
        }])
        result=_features(universe,pd.DataFrame(),pd.DataFrame())
        self.assertEqual(len(result),1)
        self.assertGreater(float(result.iloc[0]['product_age_months']),0)
        self.assertEqual(int(result.iloc[0]['sale_window_days']),27)
if __name__=='__main__':unittest.main()
