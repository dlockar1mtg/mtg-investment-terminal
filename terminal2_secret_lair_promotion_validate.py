from terminal2.secret_lair.promotion import validate_secret_lair_promotion

def main():
    result=validate_secret_lair_promotion()
    print("\nTerminal 2.9.8 Secret Lair Promotion Validation")
    print("="*64)
    print(f"Datasets checked: {result.datasets_checked}")
    print(f"Eligible products: {result.eligible_products}")
    print(f"Production registry: {result.production_registry}")
    print(f"Production prices: {result.production_prices}")
    for warning in result.warnings:
        print(f"WARNING: {warning}")
    for error in result.errors:
        print(f"ERROR: {error}")
    if not result.passed:
        raise SystemExit(1)
    print("PASS: Secret Lair production promotion is valid.")

if __name__=="__main__":
    main()
