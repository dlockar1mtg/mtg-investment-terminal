from terminal2.intelligence import (
    publish_core_investment_intelligence,
)


def main():
    result = publish_core_investment_intelligence()

    print(
        "\nTerminal 2.8.0 Phase 1 "
        "Core Investment Intelligence"
    )
    print("=" * 64)
    print(
        f"Datasets published: "
        f"{result['datasets']}"
    )
    print(
        f"Products assessed: "
        f"{result['product_count']}"
    )
    print(
        f"Strong Buy: "
        f"{result['strong_buy_count']}"
    )
    print(f"Buy: {result['buy_count']}")
    print(f"Watch: {result['watch_count']}")
    print(
        f"Executive buy list rows: "
        f"{result['buy_list_count']}"
    )
    print(
        f"Average confidence: "
        f"{result['average_confidence']:.2f}"
    )
    print(
        f"Average risk: "
        f"{result['average_risk']:.2f}"
    )
    print(
        "Warehouse root: "
        "data/warehouse/current/intelligence/"
    )


if __name__ == "__main__":
    main()
