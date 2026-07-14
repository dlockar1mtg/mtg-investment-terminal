import unittest

from terminal2.calibration.contracts import (
    CALIBRATION_DATASET_CONTRACTS,
    get_calibration_contract,
)


class CalibrationContractTests(unittest.TestCase):
    def test_contracts_are_valid(self):
        self.assertEqual(
            len(CALIBRATION_DATASET_CONTRACTS),
            8,
        )
        for (
            name,
            contract,
        ) in CALIBRATION_DATASET_CONTRACTS.items():
            self.assertEqual(name, contract.name)
            definition = contract.definition()
            self.assertEqual(
                definition.category,
                "calibration",
            )
            self.assertTrue(
                definition.primary_key
            )

    def test_unknown_contract_rejected(self):
        with self.assertRaises(KeyError):
            get_calibration_contract("missing")


if __name__ == "__main__":
    unittest.main()
