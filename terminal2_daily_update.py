from terminal2.sources.daily_prices import update_daily_prices
from terminal2.features.price_features import compute_price_features


def main():
    count, _ = update_daily_prices()
    print(f"Daily observations written: {count}")
    features = compute_price_features()
    print(f"Features refreshed: {len(features)}")


if __name__ == "__main__": main()
