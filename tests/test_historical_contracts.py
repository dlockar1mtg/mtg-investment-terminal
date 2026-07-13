import unittest

from terminal2.history.contracts import (
    HISTORICAL_DATASET_CONTRACTS,
    get_historical_contract,
)


class HistoricalContractsTests(unittest.TestCase):
    def test_contracts_are_valid(self):
        self.assertEqual(
            len(HISTORICAL_DATASET_CONTRACTS),
            len(set(HISTORICAL_DATASET_CONTRACTS)),
        )
        for name, contract in HISTORICAL_DATASET_CONTRACTS.items():
            self.assertEqual(name, contract.name)
            definition = contract.definition()
            self.assertEqual(definition.name, name)
            self.assertTrue(definition.primary_key)
            self.assertTrue(definition.expected_columns)

    def test_unknown_contract_rejected(self):
        with self.assertRaises(KeyError):
            get_historical_contract("missing_contract")


if __name__ == "__main__":
    unittest.main()
