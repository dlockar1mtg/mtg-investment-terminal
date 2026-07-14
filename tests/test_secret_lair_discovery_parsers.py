import json,unittest
from terminal2.secret_lair.discovery.parsers import parse_discovery_payload
class Tests(unittest.TestCase):
 def test_html(self):
  html=b'<a href="/us/en/product/12345/example-foil-edition">Example Drop Foil Edition</a>'
  r=parse_discovery_payload('official_html','official','https://example.com/shopall',html,'2026-07-14T00:00:00+00:00',90,{})
  self.assertEqual(len(r.catalog),1);self.assertEqual(r.catalog.iloc[0]['source_record_id'],'12345');self.assertEqual(r.catalog.iloc[0]['finish'],'foil')
 def test_scryfall(self):
  data=json.dumps([{'set':'sld','set_name':'Secret Lair Drop','set_type':'memorabilia','released_at':'2020-01-01','artist':'Artist One'}]).encode()
  r=parse_discovery_payload('scryfall_cards','scryfall','file.json',data,'2026-07-14T00:00:00+00:00',80,{})
  self.assertEqual(len(r.catalog),1);self.assertEqual(r.catalog.iloc[0]['source_record_id'],'sld')
if __name__=='__main__':unittest.main()
