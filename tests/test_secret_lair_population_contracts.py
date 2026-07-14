import unittest
from terminal2.secret_lair.population.contracts import POPULATION_CONTRACTS,get_population_contract
class T(unittest.TestCase):
 def test_contracts(self):self.assertEqual(len(POPULATION_CONTRACTS),7);[self.assertEqual(n,c.name) for n,c in POPULATION_CONTRACTS.items()]
 def test_unknown(self):
  with self.assertRaises(KeyError):get_population_contract('x')
if __name__=='__main__':unittest.main()
