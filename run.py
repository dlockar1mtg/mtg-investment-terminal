from pathlib import Path

from config import (
    INPUT_FILE,
    DISCOVERED_MODEL_INPUT_FILE,
    PRODUCT_MASTER_MODEL_INPUT_FILE,
    USE_PRODUCT_MASTER,
    DISCOVER_ALL_COLLECTOR_BOXES,
    OUTPUT_DIR,
    HISTORY_DIR,
    PORTFOLIO_BUDGET,
    SAVE_DAILY_SNAPSHOT,
    AUTO_UPDATE_PRICES_BEFORE_RUN,
)
from models.pipeline import run_full_model
from utils.io import ensure_dirs

def resolve_input_file():
    if USE_PRODUCT_MASTER and Path(PRODUCT_MASTER_MODEL_INPUT_FILE).exists():
        return PRODUCT_MASTER_MODEL_INPUT_FILE
    if DISCOVER_ALL_COLLECTOR_BOXES and Path(DISCOVERED_MODEL_INPUT_FILE).exists():
        return DISCOVERED_MODEL_INPUT_FILE
    return INPUT_FILE

def main():
    ensure_dirs([OUTPUT_DIR, HISTORY_DIR])

    if AUTO_UPDATE_PRICES_BEFORE_RUN:
        try:
            from update_prices import update_all_prices
            print("\nRefreshing source data and updating product master before scoring...")
            update_all_prices()
        except Exception as exc:
            print(f"Source refresh failed; continuing with existing cache/manual fallback. Reason: {exc}")

    input_file = resolve_input_file()
    print(f"\nScoring input file: {input_file}")

    if not Path(input_file).exists():
        print("No scoring input exists yet. Check data/product_master/product_selection_review.csv and approve products.")
        return

    results = run_full_model(
        input_file=input_file,
        output_dir=OUTPUT_DIR,
        history_dir=HISTORY_DIR,
        portfolio_budget=PORTFOLIO_BUDGET,
        save_snapshot=SAVE_DAILY_SNAPSHOT,
    )

    print("\nPrice source quality:\n")
    print(results["price_quality"].to_string(index=False))

    print("\nTop ranked collector booster displays:\n")
    display_cols = [
        "box_name",
        "approved_tcgplayer_product_id",
        "current_price",
        "price_source",
        "price_data_quality",
        "investment_score",
        "risk_adjusted_score",
        "rating",
        "buy_signal",
        "target_buy_price",
        "expected_cagr",
        "projection_confidence",
        "bear_cagr",
        "base_cagr",
        "bull_cagr",
        "bear_5yr",
        "base_5yr",
        "bull_5yr",
        "market_intelligence_score",
        "mc_median",
        "mc_p05",
        "mc_p95",
        "prob_double",
        "prob_triple",
        "prob_loss",
        "real_signal_score",
        "real_signal_confidence",
        "inventory_signal_score",
        "sales_velocity_score",
        "scarcity_signal_score",
        "price_trend_signal_score",
    ]
    available = [c for c in display_cols if c in results["ranked"].columns]
    print(results["ranked"][available].head(25).to_string(index=False))

    print(f"\nPortfolio recommendation for ${PORTFOLIO_BUDGET:,.0f}:\n")
    if len(results["portfolio"]) == 0:
        print("No approved boxes cleared the portfolio quality filter.")
    else:
        print(results["portfolio"].to_string(index=False))

    print("\nFiles created in outputs/. Product master files are in data/product_master/.")

if __name__ == "__main__":
    main()
