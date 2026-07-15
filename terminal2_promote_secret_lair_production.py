import argparse
from terminal2.secret_lair.promotion import (
    apply_secret_lair_promotion,
    build_secret_lair_promotion_plan,
)
from terminal2.secret_lair.promotion.exports import (
    publish_promotion_datasets,
)

def main():
    parser=argparse.ArgumentParser(
        description="Preview or apply guarded Secret Lair production promotion."
    )
    parser.add_argument("--apply",action="store_true")
    parser.add_argument("--replace",action="store_true")
    parser.add_argument("--minimum-confidence",type=int,default=75)
    parser.add_argument("--include-review",action="store_true")
    parser.add_argument("--allow-unknown-finish",action="store_true")
    args=parser.parse_args()

    plan=build_secret_lair_promotion_plan(
        minimum_confidence=args.minimum_confidence,
        exclude_review=not args.include_review,
        allow_unknown_finish=args.allow_unknown_finish,
    )
    publish_promotion_datasets(plan.datasets)
    summary=plan.datasets["secret_lair_promotion_summary"].iloc[0]

    print("\nTerminal 2.9.8 Production Registry Promotion")
    print("="*64)
    print("Mode: " + ("APPLY" if args.apply else "PREVIEW"))
    print(f"Master products: {summary['master_product_count']}")
    print(f"Eligible products: {summary['eligible_product_count']}")
    print(f"Rejected products: {summary['rejected_product_count']}")
    print(f"Review remaining: {summary['review_remaining_count']}")
    print(f"Eligible price rows: {summary['eligible_price_count']}")
    print(f"Current production registry: {summary['production_registry_count']}")
    print(f"Current production prices: {summary['production_price_count']}")
    print(f"Apply ready: {summary['apply_ready']}")

    if not args.apply:
        print("PREVIEW ONLY: No production files were changed.")
        print("Rerun with --apply after reviewing promotion datasets.")
        return

    result=apply_secret_lair_promotion(
        minimum_confidence=args.minimum_confidence,
        exclude_review=not args.include_review,
        allow_unknown_finish=args.allow_unknown_finish,
        replace=args.replace,
    )
    print(f"Status: {result.status}")
    print(f"Production registry rows: {result.registry_rows}")
    print(f"Production price rows: {result.price_rows}")
    print(f"Registry backup: {result.registry_backup or 'None (file did not exist)'}")
    print(f"Price backup: {result.price_backup or 'None (file did not exist)'}")
    if not result.applied:
        raise SystemExit(1)

if __name__=="__main__":
    main()
