import json
import math
import re
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from app.chroma_store import store
from app.rag import RAGService
from scripts.ingest_data import ingest_directory

FALLBACK_RESPONSE = "I can only answer from the provided PDF documents."


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9]+", (text or "").lower()))


def _safe_mean(values: list[float]) -> float:
    return float(statistics.mean(values)) if values else 0.0


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = max(0, min(len(sorted_values) - 1, math.ceil(0.95 * len(sorted_values)) - 1))
    return float(sorted_values[index])


def _metric(metric_key: str, metric_label: str, metric_value: float, unit: str, category: str) -> dict:
    return {
        "metric_key": metric_key,
        "metric_label": metric_label,
        "metric_value": float(metric_value),
        "unit": unit,
        "category": category,
    }


def evaluate_and_save(
    ground_truth_path: Path = Path("eval/ground_truth_rag.json"),
    output_path: Path = Path("eval/rag_eval_report.json"),
    top_k: int = 4,
    prompt_template_id: str = "persona_professional",
) -> dict:
    if not ground_truth_path.exists():
        raise FileNotFoundError(f"Ground truth file not found: {ground_truth_path}")

    store.seed_prompt_templates()

    docs = store.documents.get(include=[])
    if not (docs.get("ids") or []):
        ingest_directory(Path("data").resolve())

    with ground_truth_path.open("r", encoding="utf-8") as handle:
        ground_truth = json.load(handle)

    rag_service = RAGService()
    prompt_template = store.get_prompt_template(prompt_template_id)

    per_question = []
    retrieval_latencies = []
    generation_latencies = []
    total_latencies = []
    reciprocal_ranks = []
    precision_scores = []
    answer_context_overlaps = []
    expected_keyword_coverages = []

    for row in ground_truth:
        question = (row.get("question") or "").strip()
        expected_source = row.get("expected_source")
        expected_keywords = [str(item).lower() for item in row.get("expected_answer_keywords", [])]

        total_start = time.perf_counter()

        retrieval_start = time.perf_counter()
        query_embedding = rag_service.embed_text(question)
        retrieved_chunks = rag_service.find_relevant_chunks(query_embedding)
        retrieval_ms = (time.perf_counter() - retrieval_start) * 1000

        retrieved_sources = [chunk["source"] for chunk in retrieved_chunks]
        unique_sources = list(dict.fromkeys(retrieved_sources))
        top_source = unique_sources[0] if unique_sources else None

        hit_at_1 = int(top_source == expected_source) if expected_source else 0
        hit_at_3 = int(expected_source in unique_sources[:3]) if expected_source else 0
        hit_at_4 = int(expected_source in unique_sources[:4]) if expected_source else 0

        if expected_source and expected_source in unique_sources[:top_k]:
            rank = unique_sources[:top_k].index(expected_source) + 1
            reciprocal_rank = 1.0 / rank
        else:
            rank = None
            reciprocal_rank = 0.0

        context_text = "\n\n".join(chunk["chunk_text"] for chunk in retrieved_chunks)

        generation_start = time.perf_counter()
        if not retrieved_chunks:
            answer = FALLBACK_RESPONSE
        else:
            answer = rag_service.generate_answer(
                user_message=question,
                context_chunks=retrieved_chunks,
                history=[],
                prompt_template=prompt_template["template"] if prompt_template else None,
            )
        generation_ms = (time.perf_counter() - generation_start) * 1000

        total_ms = (time.perf_counter() - total_start) * 1000

        answer_tokens = _tokenize(answer)
        context_tokens = _tokenize(context_text)
        expected_tokens = set(expected_keywords)

        answer_context_overlap = (
            len(answer_tokens & context_tokens) / len(answer_tokens) if answer_tokens else 0.0
        )
        expected_keyword_coverage = (
            len(answer_tokens & expected_tokens) / len(expected_tokens) if expected_tokens else 0.0
        )

        grounded = int(answer_context_overlap >= 0.15) if answer.strip() else 0
        refused = int(FALLBACK_RESPONSE.lower() in answer.lower())
        answer_non_empty = int(bool(answer.strip()))

        precision_at_k = (
            (1.0 if expected_source in unique_sources[:top_k] else 0.0) / max(1, min(top_k, len(unique_sources)))
        )

        retrieval_latencies.append(retrieval_ms)
        generation_latencies.append(generation_ms)
        total_latencies.append(total_ms)
        reciprocal_ranks.append(reciprocal_rank)
        precision_scores.append(precision_at_k)
        answer_context_overlaps.append(answer_context_overlap)
        expected_keyword_coverages.append(expected_keyword_coverage)

        per_question.append(
            {
                "id": row.get("id"),
                "question": question,
                "expected_source": expected_source,
                "retrieved_sources": unique_sources,
                "top_source": top_source,
                "source_rank": rank,
                "hit_at_1": hit_at_1,
                "hit_at_3": hit_at_3,
                "hit_at_4": hit_at_4,
                "answer": answer,
                "answer_non_empty": answer_non_empty,
                "is_refusal": refused,
                "is_grounded": grounded,
                "answer_context_overlap": round(answer_context_overlap, 4),
                "expected_keyword_coverage": round(expected_keyword_coverage, 4),
                "retrieval_latency_ms": round(retrieval_ms, 2),
                "generation_latency_ms": round(generation_ms, 2),
                "total_latency_ms": round(total_ms, 2),
                "context_chars": len(context_text),
                "answer_chars": len(answer),
            }
        )

    total_questions = len(per_question)
    hit1 = _safe_mean([row["hit_at_1"] for row in per_question])
    hit3 = _safe_mean([row["hit_at_3"] for row in per_question])
    hit4 = _safe_mean([row["hit_at_4"] for row in per_question])

    metrics = [
        _metric("eval_total_questions", "Total Questions", total_questions, "count", "overview"),
        _metric("eval_hit_rate_at_1", "Hit Rate @1", hit1, "ratio", "retrieval"),
        _metric("eval_hit_rate_at_3", "Hit Rate @3", hit3, "ratio", "retrieval"),
        _metric("eval_hit_rate_at_4", "Hit Rate @4", hit4, "ratio", "retrieval"),
        _metric("eval_mrr_at_4", "MRR @4", _safe_mean(reciprocal_ranks), "ratio", "retrieval"),
        _metric("eval_exact_source_match_rate", "Exact Source Match", hit1, "ratio", "retrieval"),
        _metric("eval_source_precision_at_4", "Source Precision @4", _safe_mean(precision_scores), "ratio", "retrieval"),
        _metric("eval_source_recall_at_4", "Source Recall @4", hit4, "ratio", "retrieval"),
        _metric("eval_avg_retrieval_latency_ms", "Avg Retrieval Latency", _safe_mean(retrieval_latencies), "ms", "latency"),
        _metric("eval_p95_retrieval_latency_ms", "P95 Retrieval Latency", _p95(retrieval_latencies), "ms", "latency"),
        _metric("eval_avg_generation_latency_ms", "Avg Generation Latency", _safe_mean(generation_latencies), "ms", "latency"),
        _metric("eval_p95_generation_latency_ms", "P95 Generation Latency", _p95(generation_latencies), "ms", "latency"),
        _metric("eval_avg_total_latency_ms", "Avg Total Latency", _safe_mean(total_latencies), "ms", "latency"),
        _metric(
            "eval_answer_non_empty_rate",
            "Answer Non-empty Rate",
            _safe_mean([row["answer_non_empty"] for row in per_question]),
            "ratio",
            "generation",
        ),
        _metric("eval_refusal_rate", "Refusal Rate", _safe_mean([row["is_refusal"] for row in per_question]), "ratio", "generation"),
        _metric("eval_grounded_answer_rate", "Grounded Answer Rate", _safe_mean([row["is_grounded"] for row in per_question]), "ratio", "generation"),
        _metric(
            "eval_avg_answer_context_overlap",
            "Avg Answer-Context Overlap",
            _safe_mean(answer_context_overlaps),
            "ratio",
            "generation",
        ),
        _metric(
            "eval_avg_expected_keyword_coverage",
            "Avg Expected Keyword Coverage",
            _safe_mean(expected_keyword_coverages),
            "ratio",
            "generation",
        ),
        _metric("eval_avg_context_chars", "Avg Context Chars", _safe_mean([row["context_chars"] for row in per_question]), "count", "context"),
        _metric("eval_avg_answer_chars", "Avg Answer Chars", _safe_mean([row["answer_chars"] for row in per_question]), "count", "context"),
    ]

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ground_truth_path": str(ground_truth_path),
        "prompt_template_id": prompt_template_id,
        "top_k": top_k,
        "total_metrics": len(metrics),
        "metrics": metrics,
        "per_question": per_question,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    return report


if __name__ == "__main__":
    result = evaluate_and_save()
    print(f"Saved RAG evaluation report with {result['total_metrics']} metrics to eval/rag_eval_report.json")
