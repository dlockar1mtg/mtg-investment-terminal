from terminal2.db.module2_migration import migrate_module2
from terminal2.market.sources.templates import create_market_input_templates

def main():
    migrate_module2()
    result = create_market_input_templates()
    print("Module 2 database initialized.")
    print(f"Supply template: {result['supply']}")
    print(f"Sales template: {result['sales']}")
    print(f"Products included in templates: {result['products']}")

if __name__ == "__main__":
    main()
