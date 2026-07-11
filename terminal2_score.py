from terminal2.analytics.scoring import score_from_features

def main():
    ranked = score_from_features()
    print(f"Scored products: {len(ranked)}")
    cols = [c for c in [
        "box_name","latest_price","observation_count","investment_score","risk_adjusted_score",
        "rating","buy_signal","target_buy_price","expected_cagr","projection_confidence",
        "mc_median_5yr","prob_double","prob_loss"
    ] if c in ranked.columns]
    if len(ranked):
        print(ranked[cols].head(50).to_string(index=False))

if __name__ == "__main__":
    main()
