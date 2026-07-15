from terminal2.secret_lair.archive import validate_secret_lair_archive
def main():
 r=validate_secret_lair_archive();print('\nTerminal 2.10.0 Secret Lair Archive Validation');print('='*64);print(f'Datasets checked: {r.datasets_checked}');print(f'Archive observations: {r.observations}');print(f'Covered products: {r.covered_products}');print(f'Historical ready: {r.historical_ready}');[print(f'WARNING: {x}') for x in r.warnings];[print(f'ERROR: {x}') for x in r.errors]
 if not r.passed:raise SystemExit(1)
 print('PASS: Secret Lair historical market archive is valid.')
if __name__=='__main__':main()
