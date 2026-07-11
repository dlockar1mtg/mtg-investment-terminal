import pandas as pd

def create_market_summary(df):
    return pd.DataFrame([
        {"metric": "Total boxes analyzed", "value": len(df)},
        {"metric": "Average investment score", "value": round(df["investment_score"].mean(), 2)},
        {"metric": "Average risk-adjusted score", "value": round(df["risk_adjusted_score"].mean(), 2)},
        {"metric": "Average expected CAGR", "value": round(df["expected_cagr"].mean(), 4)},
        {"metric": "Average projection confidence", "value": round(df["projection_confidence"].mean(), 1)},
        {"metric": "Strong Buy / Buy count", "value": int(df["rating"].isin(["Generational Buy", "Strong Buy", "Buy"]).sum())},
        {"metric": "Accumulate count", "value": int((df["rating"] == "Accumulate").sum())},
        {"metric": "Speculative / Avoid count", "value": int(df["rating"].isin(["Speculative", "Avoid"]).sum())},
    ])
