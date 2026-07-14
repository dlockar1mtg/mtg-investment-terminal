import unittest
from terminal2.secret_lair.acquisition.contracts import ACQUISITION_CONTRACTS,get_acquisition_contract
class Tests(unittest.TestCase):
 def test_contracts(self):
  self.assertEqual(len(ACQUISITION_CONTRACTS),7)
  for n,c in ACQUISITION_CONTRACTS.items(): self.assertEqual(n,c.name); self.assertEqual(c.definition().category,'secret_lair')
 def test_unknown(self):
  with self.assertRaises(KeyError): get_acquisition_contract('missing')
if __name__=='__main__': unittest.main()
