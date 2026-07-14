from terminal2.secret_lair.pricing import (
    PRICE_PATH,
    create_price_template,
)


def main():
    path = create_price_template(PRICE_PATH)
    print(f"Secret Lair price template ready: {path}")
    print(
        "Populate this local file or use "
        "terminal2_import_secret_lair_prices.py."
    )


if __name__ == "__main__":
    main()
