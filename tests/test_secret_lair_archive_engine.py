import unittest,pandas as pd
from terminal2.secret_lair.archive.engine import _monthly,_coverage,_gaps
class T(unittest.TestCase):
 def test_monthly_coverage_and_gaps(self):
  raw=pd.DataFrame([{'observation_date':'2024-01-01','secret_lair_id':'SL-1','source_name':'tcgcsv_archive','market_price':10,'low_price':9},{'observation_date':'2024-03-01','secret_lair_id':'SL-1','source_name':'tcgcsv_archive','market_price':12,'low_price':11}]);m=_monthly(raw);p=pd.DataFrame([{'secret_lair_id':'SL-1','product_name':'A'}]);c=_coverage(raw,p);g=_gaps(m,p);self.assertEqual(len(m),2);self.assertEqual(int(c.iloc[0]['month_count']),2);self.assertEqual(g.iloc[0]['missing_month'],'2024-02')
if __name__=='__main__':unittest.main()
