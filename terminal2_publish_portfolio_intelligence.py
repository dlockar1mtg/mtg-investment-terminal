import argparse

from terminal2.portfolio import publish_portfolio_intelligence


def main():
    parser = argparse.ArgumentParser(
        description="Publish Terminal 2.5.4 portfolio intelligence."
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=10000.0,
        help="Model allocation capital. Default: 10000.",
    )
    parser.add_argument(
        "--positions",
        type=int,
        default=12,
        help="Maximum model portfolio positions. Default: 12.",
    )
    args = parser.parse_args()

    result = publish_portfolio_intelligence(
        model_capital=args.capital,
        maximum_positions=args.positions,
    )

    print("\nTerminal 2.5.4 Portfolio Intelligence")
    print("=" * 54)
    print(f"Datasets published: {result['datasets']}")
    print(
        f"Holdings file found: "
        f"{result['holdings_file_found']}"
    )
    print(f"Actual positions: {result['position_count']}")
    print(f"Model candidates: {result['candidate_count']}")
    print(
        f"Recommendations: "
        f"{result['recommendation_count']}"
    )
    print(f"Model capital: ${result['model_capital']:,.2f}")


if __name__ == "__main__":
    main()
