from terminal2.market.sources.templates import create_market_input_templates

def main():
    result = create_market_input_templates()
    print("Market input templates created.")
    print(f"Supply: {result['supply']}")
    print(f"Sales: {result['sales']}")
    print(f"Products: {result['products']}")

if __name__ == "__main__":
    main()
