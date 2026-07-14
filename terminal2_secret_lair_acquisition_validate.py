from terminal2.secret_lair.acquisition import validate_secret_lair_acquisition

def main():
    r=validate_secret_lair_acquisition()
    print("\nTerminal 2.7.0 Secret Lair Acquisition Validation")
    print("="*62)
    print(f"Datasets checked: {r.datasets_checked}")
    print(f"Catalog rows: {r.catalog_rows}")
    print(f"Conflict rows: {r.conflict_rows}")
    for w in r.warnings: print(f"WARNING: {w}")
    for e in r.errors: print(f"ERROR: {e}")
    if not r.passed: raise SystemExit(1)
    print("PASS: Secret Lair source acquisition and catalog population are valid.")
if __name__=='__main__': main()
