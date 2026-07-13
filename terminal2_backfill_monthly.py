import argparse
from terminal2.config import DEFAULT_MONTHLY_START
from terminal2.sources.tcgcsv_archive import backfill_monthly
from terminal2.features.price_features import compute_price_features
from terminal2.history import publish_historical_intelligence

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=DEFAULT_MONTHLY_START)
    parser.add_argument("--end", default=None)
    parser.add_argument("--sleep", type=float, default=0.25)
    args = parser.parse_args()

    audit = backfill_monthly(args.start, args.end, sleep_seconds=args.sleep)
    print("\nBackfill audit:")
    print(audit.to_string(index=False))

    features = compute_price_features()
    print(f"\nRecomputed historical features: {len(features)}")
    published = publish_historical_intelligence(
        recompute_features=False
    )
    print(f"Published historical datasets: {published['datasets']}")

if __name__ == "__main__":
    main()
