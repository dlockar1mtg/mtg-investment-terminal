import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from config import OUTPUT_DIR

st.set_page_config(page_title="MTG Investment Terminal", layout="wide")

st.title("MTG Investment Terminal")

ranked_path = OUTPUT_DIR / "ranked_boxes.csv"
portfolio_path = OUTPUT_DIR / "portfolio_recommendation.csv"
audit_path = OUTPUT_DIR / "projection_audit.csv"

if not ranked_path.exists():
    st.warning("Run `python run.py` first to generate output files.")
    st.stop()

ranked = pd.read_csv(ranked_path)

st.subheader("Market Overview")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Boxes Analyzed", len(ranked))
c2.metric("Avg Risk-Adjusted Score", f"{ranked['risk_adjusted_score'].mean():.1f}")
c3.metric("Avg Expected CAGR", f"{ranked['expected_cagr'].mean():.1%}")
c4.metric("Avg Confidence", f"{ranked['projection_confidence'].mean():.1f}")

st.subheader("Top Ranked Boxes")
st.dataframe(
    ranked[
        [
            "box_name",
            "current_price",
            "investment_score",
            "risk_adjusted_score",
            "rating",
            "buy_signal",
            "expected_cagr",
            "projection_confidence",
            "bear_5yr",
            "base_5yr",
            "bull_5yr",
        ]
    ],
    use_container_width=True,
)

st.subheader("Risk-Adjusted Score vs Expected CAGR")
fig = px.scatter(
    ranked,
    x="risk_adjusted_score",
    y="expected_cagr",
    size="projection_confidence",
    color="set_type",
    hover_name="box_name",
)
st.plotly_chart(fig, use_container_width=True)

st.subheader("5-Year Projection Range")
projection_df = ranked[["box_name", "bear_5yr", "base_5yr", "bull_5yr"]].head(12)
st.bar_chart(projection_df.set_index("box_name"))

if portfolio_path.exists():
    st.subheader("Portfolio Recommendation")
    portfolio = pd.read_csv(portfolio_path)
    st.dataframe(portfolio, use_container_width=True)

if audit_path.exists():
    st.subheader("Projection Audit")
    audit = pd.read_csv(audit_path)
    st.dataframe(audit, use_container_width=True)
