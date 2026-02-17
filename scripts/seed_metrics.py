from app.db import Base, SessionLocal, engine
from app.models import LogMetric


METRICS = [
    ("total_logins", "Total Logins", 1240, "count", "auth"),
    ("failed_logins", "Failed Logins", 74, "count", "auth"),
    ("active_users_24h", "Active Users (24h)", 317, "count", "usage"),
    ("new_users_7d", "New Users (7d)", 92, "count", "usage"),
    ("total_chats", "Total Chats", 2860, "count", "chat"),
    ("messages_24h", "Messages (24h)", 1482, "count", "chat"),
    ("avg_messages_per_chat", "Avg Messages / Chat", 8.4, "ratio", "chat"),
    ("avg_response_ms", "Avg Response Time", 1260, "ms", "latency"),
    ("p95_response_ms", "P95 Response Time", 2910, "ms", "latency"),
    ("timeout_errors", "Timeout Errors", 12, "count", "errors"),
    ("db_errors", "DB Errors", 4, "count", "errors"),
    ("api_errors", "API Errors", 9, "count", "errors"),
    ("retrieval_hits", "Retrieval Hits", 1112, "count", "rag"),
    ("retrieval_misses", "Retrieval Misses", 198, "count", "rag"),
    ("avg_context_chunks", "Avg Context Chunks", 3.6, "count", "rag"),
    ("embedding_calls", "Embedding Calls", 1675, "count", "openai"),
    ("chat_completion_calls", "Chat Completion Calls", 1320, "count", "openai"),
    ("openai_cost_usd", "OpenAI Cost", 48.27, "usd", "openai"),
    ("token_input_total", "Input Tokens", 943200, "count", "openai"),
    ("token_output_total", "Output Tokens", 422450, "count", "openai"),
]


def seed_metrics() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.query(LogMetric).delete()
        db.commit()

        for key, label, value, unit, category in METRICS:
            db.add(
                LogMetric(
                    metric_key=key,
                    metric_label=label,
                    metric_value=float(value),
                    unit=unit,
                    category=category,
                )
            )

        db.commit()
        print("Inserted 20 log metrics into log_metrics table.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_metrics()
