import unittest
from terminal2.secret_lair.archive.contracts import ARCHIVE_CONTRACTS,get_archive_contract
class T(unittest.TestCase):
 def test_contracts(self):self.assertEqual(len(ARCHIVE_CONTRACTS),9)
 def test_unknown(self):
  with self.assertRaises(KeyError):get_archive_contract('x')
if __name__=='__main__':unittest.main()
