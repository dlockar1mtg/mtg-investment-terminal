from terminal2.secret_lair.population import validate_secret_lair_population
def main():
 r=validate_secret_lair_population();print("\nTerminal 2.9.6 Secret Lair Population Validation");print("="*64);print(f"Datasets checked: {r.datasets_checked}");print(f"Catalog rows: {r.catalog_rows}");print(f"Proposed registry assets: {r.registry_assets}");print(f"Scoring-ready assets: {r.scoring_ready_assets}")
 for x in r.warnings:print(f"WARNING: {x}")
 for x in r.errors:print(f"ERROR: {x}")
 if not r.passed:raise SystemExit(1)
 print("PASS: Secret Lair population outputs are valid.")
if __name__=='__main__':main()
