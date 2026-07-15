import unittest
from terminal2.secret_lair.master_database.contracts import MASTER_DATABASE_CONTRACTS,get_master_database_contract
class T(unittest.TestCase):
 def test_contracts(self):
  self.assertEqual(len(MASTER_DATABASE_CONTRACTS),8)
  for n,c in MASTER_DATABASE_CONTRACTS.items():self.assertEqual(n,c.name);self.assertTrue(c.primary_key)
 def test_unknown(self):
  with self.assertRaises(KeyError):get_master_database_contract("missing")
if __name__=="__main__":unittest.main()
