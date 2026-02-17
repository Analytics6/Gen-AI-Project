from collections import defaultdict

import pandas as pd
import streamlit as st
from sqlalchemy import desc

from app.db import Base, SessionLocal, engine
from app.models import LogMetric


st.set_page_config(page_title="RAG Metrics Dashboard", layout="wide")
st.title("RAG Chatbot Metrics Dashboard")
st.caption("Live metrics from the `log_metrics` table")

Base.metadata.create_all(bind=engine)

db = SessionLocal()
try:
    metrics = db.query(LogMetric).order_by(desc(LogMetric.created_at), LogMetric.id).all()
finally:
    db.close()

if not metrics:
    st.warning("No metrics found. Run: python -m scripts.seed_metrics")
    st.stop()

rows = [
    {
        "metric_key": metric.metric_key,
        "metric_label": metric.metric_label,
        "metric_value": metric.metric_value,
        "unit": metric.unit,
        "category": metric.category,
        "created_at": metric.created_at,
    }
    for metric in metrics
]
df = pd.DataFrame(rows)

latest_by_key = df.sort_values(by=["created_at"], ascending=False).drop_duplicates(subset=["metric_key"])
latest_by_key = latest_by_key.sort_values(by=["category", "metric_label"])

st.subheader("KPI Cards")
card_columns = st.columns(4)
for index, (_, row) in enumerate(latest_by_key.iterrows()):
    column = card_columns[index % 4]
    value = row["metric_value"]
    if row["unit"] == "ms":
        display = f"{value:,.0f} ms"
    elif row["unit"] == "usd":
        display = f"${value:,.2f}"
    elif row["unit"] == "ratio":
        display = f"{value:,.2f}"
    else:
        display = f"{value:,.0f}"
    column.metric(label=row["metric_label"], value=display)

st.subheader("Metrics by Category")
categories = sorted(latest_by_key["category"].unique().tolist())
selected_category = st.selectbox("Filter Category", options=["all"] + categories, index=0)

filtered = latest_by_key if selected_category == "all" else latest_by_key[latest_by_key["category"] == selected_category]
chart_df = filtered[["metric_label", "metric_value"]].set_index("metric_label")
st.bar_chart(chart_df)

st.subheader("All Log Metrics (Table)")
st.dataframe(
    latest_by_key[["metric_key", "metric_label", "metric_value", "unit", "category", "created_at"]],
    use_container_width=True,
)

st.subheader("Metric Counts")
summary = defaultdict(int)
summary["total_saved_metrics"] = int(len(metrics))
summary["unique_metric_keys"] = int(latest_by_key["metric_key"].nunique())
summary_df = pd.DataFrame(
    [{"name": key, "value": value} for key, value in summary.items()]
)
st.table(summary_df)
