import json
from typing import Sequence

import numpy as np
from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import settings
from app.models import DocumentChunk


class RAGService:
    def __init__(self):
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not configured")
        self.client = OpenAI(api_key=settings.openai_api_key)

    def embed_text(self, text: str) -> list[float]:
        response = self.client.embeddings.create(
            model=settings.openai_embedding_model,
            input=text,
        )
        return response.data[0].embedding

    def find_relevant_chunks(self, db: Session, query_embedding: Sequence[float]) -> list[DocumentChunk]:
        chunks = db.query(DocumentChunk).all()
        if not chunks:
            return []

        query_vec = np.array(query_embedding, dtype=np.float32)
        scored: list[tuple[float, DocumentChunk]] = []

        for chunk in chunks:
            chunk_vec = np.array(json.loads(chunk.embedding_json), dtype=np.float32)
            denom = np.linalg.norm(query_vec) * np.linalg.norm(chunk_vec)
            score = float(np.dot(query_vec, chunk_vec) / denom) if denom else 0.0
            scored.append((score, chunk))

        scored.sort(key=lambda value: value[0], reverse=True)
        return [chunk for _, chunk in scored[: settings.rag_top_k]]

    def generate_answer(self, user_message: str, context_chunks: list[DocumentChunk], history: list[dict]) -> str:
        context = "\n\n".join([f"Source: {c.source}\n{c.chunk_text}" for c in context_chunks])
        system_prompt = (
            "You are a helpful enterprise assistant. Use provided context when relevant. "
            "If the answer is not in context, say so clearly and provide best-effort guidance."
        )

        messages = [{"role": "system", "content": system_prompt}]
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append(
            {
                "role": "user",
                "content": (
                    "Context:\n"
                    f"{context if context else 'No relevant context found.'}\n\n"
                    "Question:\n"
                    f"{user_message}"
                ),
            }
        )

        response = self.client.chat.completions.create(
            model=settings.openai_chat_model,
            messages=messages,
            temperature=0.2,
        )
        return response.choices[0].message.content or "I could not generate a response."
