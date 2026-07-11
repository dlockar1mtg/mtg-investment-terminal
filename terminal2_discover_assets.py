from terminal2.sources.product_discovery import discover_supported_products
from terminal2.assets.product_master2 import merge_candidates


def main():
    discovered = discover_supported_products()
    if discovered.empty:
        print("No supported candidates discovered.")
        return
    print("\nDiscovered candidates by type:")
    print(discovered.groupby("investment_product_type").size().to_string())
    master, added = merge_candidates()
    print(f"\nAdded to Product Master: {len(added)}")
    print(f"Total Product Master rows: {len(master)}")
    print("Secret Lairs remain review_required until their sealed product identity is verified.")


if __name__ == "__main__": main()
