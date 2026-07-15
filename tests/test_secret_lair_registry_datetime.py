import unittest
import pandas as pd
from terminal2.secret_lair.registry import _release_calendar

class SecretLairRegistryDatetimeTests(unittest.TestCase):
    def test_release_calendar_accepts_mixed_timezone_dates(self):
        registry=pd.DataFrame([{
            'secret_lair_id':'SL-1','drop_name':'Test',
            'release_date':'2022-04-01T07:00:00Z',
            'sale_start_date':'2022-03-01',
            'sale_end_date':'2022-03-15T23:59:59Z',
            'superdrop_name':'','event_type':'drop','status':'released'
        }])
        result=_release_calendar(registry)
        self.assertEqual(int(result.iloc[0]['release_year']),2022)
        self.assertEqual(int(result.iloc[0]['sale_window_days']),14)
if __name__=='__main__':unittest.main()
