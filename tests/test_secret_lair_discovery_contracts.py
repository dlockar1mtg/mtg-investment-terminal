import unittest
from terminal2.secret_lair.discovery.contracts import DISCOVERY_CONTRACTS,get_discovery_contract
class Tests(unittest.TestCase):
 def test_contracts(self):
  self.assertEqual(len(DISCOVERY_CONTRACTS),7)
  for n,c in DISCOVERY_CONTRACTS.items():self.assertEqual(n,c.name);self.assertEqual(c.definition().category,'secret_lair')
 def test_unknown(self):
  with self.assertRaises(KeyError):get_discovery_contract('missing')
if __name__=='__main__':unittest.main()
