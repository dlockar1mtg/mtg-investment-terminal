from pathlib import Path
import tempfile,unittest,pandas as pd
from terminal2.secret_lair.discovery.engine import discover_secret_lairs
class Tests(unittest.TestCase):
 def test_local_html(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);html=root/'shop.html';cfg=root/'config.csv';html.write_text('<a href="/product/100/example-nonfoil">Example Drop Nonfoil Edition</a>')
   pd.DataFrame([{'source_name':'official','connector_type':'local_html','endpoint':str(html),'enabled':'true','priority':1,'parser_name':'official_html','timeout_seconds':5,'max_retries':1,'cache_ttl_hours':1,'source_quality':90,'query_json':'{}'}]).to_csv(cfg,index=False)
   r=discover_secret_lairs(cfg);self.assertEqual(len(r.datasets['secret_lair_discovery_catalog']),1);self.assertEqual(len(r.datasets['secret_lair_discovery_candidates']),1)
if __name__=='__main__':unittest.main()
