import unittest
from terminal2.secret_lair.promotion.contracts import (
    PROMOTION_CONTRACTS,get_promotion_contract
)
class T(unittest.TestCase):
    def test_contracts(self):
        self.assertEqual(len(PROMOTION_CONTRACTS),7)
        for name,contract in PROMOTION_CONTRACTS.items():
            self.assertEqual(name,contract.name)
            self.assertTrue(contract.primary_key)
    def test_unknown(self):
        with self.assertRaises(KeyError):
            get_promotion_contract("missing")
if __name__=="__main__":unittest.main()
