import unittest

from terminal2.forecast.contracts import (
    FORECAST_DATASET_CONTRACTS,
    get_forecast_contract,
)


class ForecastContractsTests(unittest.TestCase):
    def test_contracts_are_valid(self):
        for name, contract in FORECAST_DATASET_CONTRACTS.items():
            self.assertEqual(name, contract.name)
            definition = contract.definition()
            self.assertEqual(definition.name, name)
            self.assertTrue(definition.primary_key)
            self.assertTrue(definition.expected_columns)

    def test_unknown_contract_rejected(self):
        with self.assertRaises(KeyError):
            get_forecast_contract("missing_contract")


if __name__ == "__main__":
    unittest.main()
