from terminal2.portfolio.engine import create_holdings_template


def main():
    path = create_holdings_template()
    print(f"Portfolio holdings template ready: {path}")
    print(
        "Copy the template to portfolio_holdings.csv, "
        "replace the example row, and keep that personal file out of Git."
    )


if __name__ == "__main__":
    main()
