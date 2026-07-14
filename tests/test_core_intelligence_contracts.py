import unittest

from terminal2.intelligence.contracts import (
    INTELLIGENCE_DATASET_CONTRACTS,
    get_intelligence_contract,
)


class CoreIntelligenceContractTests(unittest.TestCase):
    def test_contracts_are_valid(self):
        self.assertEqual(
            len(INTELLIGENCE_DATASET_CONTRACTS),
            7,
        )
        for (
            name,
            contract,
        ) in INTELLIGENCE_DATASET_CONTRACTS.items():
            self.assertEqual(name, contract.name)
            definition = contract.definition()
            self.assertEqual(
                definition.category,
                "intelligence",
            )
            self.assertTrue(
                definition.primary_key
            )
            self.assertTrue(
                definition.expected_columns
            )

    def test_unknown_contract_rejected(self):
        with self.assertRaises(KeyError):
            get_intelligence_contract(
                "missing_contract"
            )


if __name__ == "__main__":
    unittest.main()
