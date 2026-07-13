import unittest

from terminal2.secret_lair.contracts import (
    SECRET_LAIR_DATASET_CONTRACTS,
    get_secret_lair_contract,
)


class SecretLairContractsTests(unittest.TestCase):
    def test_contracts_are_valid(self):
        self.assertEqual(
            len(SECRET_LAIR_DATASET_CONTRACTS),
            7,
        )
        for name, contract in (
            SECRET_LAIR_DATASET_CONTRACTS.items()
        ):
            self.assertEqual(name, contract.name)
            definition = contract.definition()
            self.assertEqual(
                definition.category,
                "secret_lair",
            )
            self.assertTrue(definition.primary_key)
            self.assertTrue(definition.expected_columns)

    def test_unknown_contract_rejected(self):
        with self.assertRaises(KeyError):
            get_secret_lair_contract("missing_contract")


if __name__ == "__main__":
    unittest.main()
