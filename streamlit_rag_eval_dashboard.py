import json
from pathlib import Path

import pandas as pd
import streamlit as st

from scripts.evaluate_rag import evaluate_and_save

REPORT_PATH = Path("eval/rag_eval_report.json")
GROUND_TRUTH_PATH = Path("eval/ground_truth_rag.json")


st.set_page_config(page_title="RAG Evaluation Dashboard", layout="wide")
st.title("RAG Model Evaluation Dashboard")
st.caption("Ground-truth based evaluation for PDF-only retrieval and response quality")

col1, col2, col3 = st.columns([1, 1, 2])
with col1:
    top_k = st.selectbox("Top-K", options=[3, 4, 5], index=1)
with col2:
    prompt_template_id = st.selectbox(
        "Prompt Persona",
        options=["persona_professional", "persona_empathetic", "persona_resolution"],
        index=0,
    )
with col3:
    st.write("")
    run_eval = st.button("Run RAG Evaluation", type="primary", use_container_width=True)

if run_eval:
    with st.spinner("Running evaluation across ground truth set..."):
        try:
            report = evaluate_and_save(
                ground_truth_path=GROUND_TRUTH_PATH,
                output_path=REPORT_PATH,
                top_k=int(top_k),
                prompt_template_id=prompt_template_id,
            )
            st.success(f"Evaluation complete. Published {report.get('total_metrics', 0)} metrics.")
        except Exception as error:
            st.error(f"Evaluation failed: {error}")

if not REPORT_PATH.exists():
    st.info("No report found yet. Click 'Run RAG Evaluation' to generate metrics.")
    st.stop()

with REPORT_PATH.open("r", encoding="utf-8") as handle:
    report = json.load(handle)

metrics_df = pd.DataFrame(report.get("metrics", []))
questions_df = pd.DataFrame(report.get("per_question", []))

if metrics_df.empty:
    st.warning("Metrics are empty. Re-run evaluation.")
    st.stop()

st.subheader("Published Metrics (20)")
card_columns = st.columns(4)
for index, (_, row) in enumerate(metrics_df.iterrows()):
    column = card_columns[index % 4]
    value = row["metric_value"]
    unit = row["unit"]

    if unit == "ms":
        display = f"{value:,.2f} ms"
    elif unit == "ratio":
        display = f"{value:.3f}"
    else:
        display = f"{value:,.2f}" if float(value) % 1 else f"{int(value):,}"

    column.metric(label=row["metric_label"], value=display)

st.subheader("Metrics by Category")
chart_df = metrics_df[["metric_label", "metric_value"]].set_index("metric_label")
st.bar_chart(chart_df)

st.subheader("Metrics Table")
st.dataframe(metrics_df, use_container_width=True)

if not questions_df.empty:
    st.subheader("Per-question Evaluation Details")
    display_columns = [
        "id",
        "question",
        "expected_source",
        "top_source",
        "source_rank",
        "hit_at_1",
        "hit_at_3",
        "hit_at_4",
        "is_grounded",
        "is_refusal",
        "expected_keyword_coverage",
        "answer_context_overlap",
        "retrieval_latency_ms",
        "generation_latency_ms",
        "total_latency_ms",
    ]
    available_columns = [column for column in display_columns if column in questions_df.columns]
    st.dataframe(questions_df[available_columns], use_container_width=True)

    with st.expander("Show Generated Answers"):
        for _, row in questions_df.iterrows():
            st.markdown(f"**{row.get('id', '')}** - {row.get('question', '')}")
            st.caption(f"Expected source: {row.get('expected_source', 'n/a')}")
            st.write(row.get("answer", ""))
            st.divider()
