from utils.io import read_input_csv, write_csv, save_price_snapshot
from models.source_data import refresh_price_data, create_price_quality_report
from models.scoring import calculate_investment_score, add_ratings_and_signals
from models.projections import add_projections
from models.optimizer import optimize_portfolio
from models.audit import create_projection_audit
from models.market_summary import create_market_summary
from config import REFRESH_SOURCE_DATA, ALLOW_STALE_PRICE_FALLBACK

def run_full_model(input_file, output_dir, history_dir, portfolio_budget, save_snapshot=True):
    df = read_input_csv(input_file)

    if REFRESH_SOURCE_DATA:
        df = refresh_price_data(df, allow_stale_fallback=ALLOW_STALE_PRICE_FALLBACK)

    price_quality = create_price_quality_report(df)
    write_csv(price_quality, output_dir / "price_quality_report.csv")

    df = calculate_investment_score(df)
    df = add_projections(df)
    df = add_ratings_and_signals(df)

    ranked = df.sort_values(
        by=["risk_adjusted_score", "investment_score", "expected_cagr"],
        ascending=False
    ).reset_index(drop=True)

    portfolio = optimize_portfolio(ranked, portfolio_budget)
    audit = create_projection_audit(ranked)
    summary = create_market_summary(ranked)

    write_csv(ranked, output_dir / "ranked_boxes.csv")
    write_csv(portfolio, output_dir / "portfolio_recommendation.csv")
    write_csv(audit, output_dir / "projection_audit.csv")
    write_csv(summary, output_dir / "market_summary.csv")

    if save_snapshot:
        save_price_snapshot(ranked, history_dir)

    return {
        "ranked": ranked,
        "portfolio": portfolio,
        "audit": audit,
        "summary": summary,
        "price_quality": price_quality,
    }
