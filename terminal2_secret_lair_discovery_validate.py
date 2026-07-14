from terminal2.secret_lair.discovery import validate_secret_lair_discovery
def main():
    r=validate_secret_lair_discovery();print('\nTerminal 2.7.1 Secret Lair Discovery Validation');print('='*62);print(f'Datasets checked: {r.datasets_checked}');print(f'Discovered rows: {r.discovered_rows}');print(f'Conflict rows: {r.conflict_rows}')
    [print(f'WARNING: {x}') for x in r.warnings];[print(f'ERROR: {x}') for x in r.errors]
    if not r.passed:raise SystemExit(1)
    print('PASS: Automated Secret Lair discovery is valid.')
if __name__=='__main__':main()
