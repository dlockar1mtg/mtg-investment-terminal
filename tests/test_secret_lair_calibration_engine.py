import unittest
import pandas as pd
from terminal2.secret_lair.calibration.engine import calibrate_secret_lair_intelligence

class T(unittest.TestCase):
 def frames(self):
  features=pd.DataFrame([
   {"investment_product_id":"SL-1","asset_class":"Secret Lair","product_name":"Priced A","current_price":50,"observation_count":1,"source_count":1,"history_span_days":0,"metadata_completeness":75,"msrp_usd":0,"artist_count":0,"universes_beyond_flag":False,"liquidity_score":13,"scarcity_score":40},
   {"investment_product_id":"SL-2","asset_class":"Secret Lair","product_name":"Priced B","current_price":100,"observation_count":1,"source_count":1,"history_span_days":0,"metadata_completeness":50,"msrp_usd":0,"artist_count":0,"universes_beyond_flag":False,"liquidity_score":10,"scarcity_score":30},
   {"investment_product_id":"SL-3","asset_class":"Secret Lair","product_name":"Unpriced","current_price":0,"observation_count":0,"source_count":0,"history_span_days":0,"metadata_completeness":50,"msrp_usd":0,"artist_count":0,"universes_beyond_flag":False,"liquidity_score":0,"scarcity_score":30},
  ])
  scores=pd.DataFrame({"investment_product_id":["SL-1","SL-2","SL-3"],"investment_score":[38,34,32],"risk_adjusted_score":[40,36,30],"scarcity_score":[45,30,30]})
  risk=pd.DataFrame({"investment_product_id":["SL-1","SL-2","SL-3"],"overall_risk_score":[40,45,55]})
  conf=pd.DataFrame({"investment_product_id":["SL-1","SL-2","SL-3"],"overall_confidence_score":[32,32,18]})
  cov=pd.DataFrame({"investment_product_id":["SL-1","SL-2","SL-3"],"model_coverage_score":[50,50,25]})
  prices=pd.DataFrame([
   {"secret_lair_id":"1","market_price":50,"low_price":48},
   {"secret_lair_id":"2","market_price":100,"low_price":80},
  ])
  return features,scores,risk,conf,cov,prices
 def test_current_price_only_never_buy(self):
  r=calibrate_secret_lair_intelligence(*self.frames())
  rec=r.calibrated_recommendations
  current=rec[rec["evidence_tier"].eq("Current Price Only")]
  self.assertFalse(current["recommendation"].isin(["Buy","Strong Buy"]).any())
  self.assertEqual(rec.loc[rec["investment_product_id"].eq("SL-3"),"recommendation"].iloc[0],"Insufficient Data")
 def test_scores_gain_discrimination(self):
  r=calibrate_secret_lair_intelligence(*self.frames())
  self.assertGreater(r.calibrated_scores["calibrated_investment_score"].nunique(),1)
if __name__=="__main__":unittest.main()
