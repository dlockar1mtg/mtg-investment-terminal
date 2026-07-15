from terminal2.secret_lair.master_database import validate_master_secret_lair_database

def main():
 r=validate_master_secret_lair_database();print("\nTerminal 2.9.7 Master Secret Lair Database Validation");print("="*64);print(f"Datasets checked: {r.datasets_checked}");print(f"Canonical products: {r.canonical_products}");print(f"Current prices: {r.current_prices}");print(f"Review rows: {r.review_rows}")
 for x in r.warnings:print(f"WARNING: {x}")
 for x in r.errors:print(f"ERROR: {x}")
 if not r.passed:raise SystemExit(1)
 print("PASS: Master Secret Lair Database is valid.")
if __name__=="__main__":main()
