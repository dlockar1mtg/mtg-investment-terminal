import unittest

from terminal2.semantic.contracts import (
    SEMANTIC_DATASET_CONTRACTS,
    get_semantic_contract,
)


class SemanticContractsTests(unittest.TestCase):
    def test_contracts_are_valid(self):
        self.assertEqual(len(SEMANTIC_DATASET_CONTRACTS), 11)
        for name, contract in SEMANTIC_DATASET_CONTRACTS.items():
            self.assertEqual(name, contract.name)
            definition = contract.definition()
            self.assertEqual(definition.category, "semantic")
            self.assertTrue(definition.primary_key)
            self.assertTrue(definition.expected_columns)

    def test_unknown_contract_rejected(self):
        with self.assertRaises(KeyError):
            get_semantic_contract("missing_contract")


if __name__ == "__main__":
    unittest.main()
