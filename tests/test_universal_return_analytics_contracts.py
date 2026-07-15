import unittest

from terminal2.return_analytics.contracts import (
    RETURN_ANALYTICS_CONTRACTS,
    get_return_analytics_contract,
)


class UniversalReturnAnalyticsContractTests(unittest.TestCase):
    def test_contracts(self):
        self.assertEqual(len(RETURN_ANALYTICS_CONTRACTS), 9)
        for name, contract in RETURN_ANALYTICS_CONTRACTS.items():
            self.assertEqual(name, contract.name)

    def test_unknown(self):
        with self.assertRaises(KeyError):
            get_return_analytics_contract("missing")


if __name__ == "__main__":
    unittest.main()
