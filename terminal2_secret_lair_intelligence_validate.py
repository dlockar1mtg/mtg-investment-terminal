from terminal2.secret_lair.intelligence_expansion import validate_secret_lair_intelligence_expansion
def main():
 r=validate_secret_lair_intelligence_expansion();print('\nTerminal 2.9.5 Secret Lair Intelligence Validation');print('='*64);print(f'Datasets checked: {r.datasets_checked}');print(f'Secret Lair assets: {r.secret_lair_assets}');print(f'Unified products: {r.unified_products}');[print(f'WARNING: {x}') for x in r.warnings];[print(f'ERROR: {x}') for x in r.errors];
 if not r.passed:raise SystemExit(1)
 print('PASS: Secret Lair intelligence expansion is valid.')
if __name__=='__main__':main()
