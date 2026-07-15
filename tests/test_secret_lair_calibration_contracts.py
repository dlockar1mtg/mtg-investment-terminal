import unittest
from terminal2.secret_lair.calibration.contracts import CALIBRATION_CONTRACTS,get_calibration_contract
class T(unittest.TestCase):
 def test_contracts(self):
  self.assertEqual(len(CALIBRATION_CONTRACTS),5)
  for n,c in CALIBRATION_CONTRACTS.items():self.assertEqual(n,c.name)
 def test_unknown(self):
  with self.assertRaises(KeyError):get_calibration_contract("missing")
if __name__=="__main__":unittest.main()
