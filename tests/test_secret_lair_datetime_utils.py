import unittest
import pandas as pd
from terminal2.secret_lair.datetime_utils import (
    date_string_series,to_utc_naive_scalar,to_utc_naive_series,utc_naive_today,
)

class SecretLairDatetimeUtilsTests(unittest.TestCase):
    def test_mixed_series_normalizes_to_utc_naive(self):
        values=pd.Series(["2021-03-01T08:00:00Z","2021-03-01",None])
        result=to_utc_naive_series(values)
        self.assertIsNone(result.dt.tz)
        self.assertEqual(result.iloc[0],pd.Timestamp("2021-03-01 08:00:00"))
        self.assertEqual(result.iloc[1],pd.Timestamp("2021-03-01 00:00:00"))
        self.assertTrue(pd.isna(result.iloc[2]))
    def test_scalar_and_date_strings(self):
        scalar=to_utc_naive_scalar("2022-01-01T12:30:00-05:00")
        self.assertEqual(scalar,pd.Timestamp("2022-01-01 17:30:00"))
        dates=date_string_series(pd.Series(["2022-01-01T12:30:00Z"]))
        self.assertEqual(dates.iloc[0],"2022-01-01")
    def test_today_is_naive_and_normalized(self):
        today=utc_naive_today()
        self.assertIsNone(today.tzinfo)
        self.assertEqual(today,today.normalize())
if __name__=='__main__':unittest.main()
