import unittest
from terminal2.secret_lair.intelligence_expansion.contracts import EXPANSION_CONTRACTS,get_expansion_contract
class T(unittest.TestCase):
 def test_contracts(self):self.assertEqual(len(EXPANSION_CONTRACTS),14);[self.assertTrue(c.primary_key) for c in EXPANSION_CONTRACTS.values()]
 def test_unknown(self):
  with self.assertRaises(KeyError):get_expansion_contract('x')
if __name__=='__main__':unittest.main()
