from terminal2.market.sources.importers import import_all_market_inputs

def main():
    result = import_all_market_inputs()
    print("\nMarket input import results:")
    print(f"Supply: {result['supply']}")
    print(f"Sales: {result['sales']}")

if __name__ == "__main__":
    main()
