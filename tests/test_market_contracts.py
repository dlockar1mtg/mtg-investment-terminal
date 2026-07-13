import unittest

from terminal2.market.contracts import (
    MARKET_DATASET_CONTRACTS,
    get_market_contract,
)


class MarketContractsTests(unittest.TestCase):
    def test_contracts_are_unique_and_valid(self):
        self.assertEqual(
            len(MARKET_DATASET_CONTRACTS),
            len(set(MARKET_DATASET_CONTRACTS)),
        )
        for name, contract in MARKET_DATASET_CONTRACTS.items():
            self.assertEqual(name, contract.name)
            definition = contract.definition()
            self.assertEqual(definition.name, name)
            self.assertTrue(definition.expected_columns)

    def test_unknown_contract_rejected(self):
        with self.assertRaises(KeyError):
            get_market_contract("missing_contract")


if __name__ == "__main__":
    unittest.main()
