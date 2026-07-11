import argparse
from terminal2.config import DEFAULT_MONTHLY_START
from terminal2.sources.tcgcsv_archive import backfill_monthly

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=DEFAULT_MONTHLY_START)
    parser.add_argument("--end", default=None)
    parser.add_argument("--sleep", type=float, default=0.25)
    args = parser.parse_args()

    audit = backfill_monthly(args.start, args.end, sleep_seconds=args.sleep)
    print("\nBackfill audit:")
    print(audit.to_string(index=False))

if __name__ == "__main__":
    main()
