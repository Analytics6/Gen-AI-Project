from openai import OpenAI

from app.chroma_store import store
from app.config import settings


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

    def find_relevant_chunks(self, query_embedding: list[float]) -> list[dict]:
        return store.query_document_chunks(query_embedding=query_embedding, top_k=settings.rag_top_k)

    def generate_answer(
        self,
        user_message: str,
        context_chunks: list[dict],
        history: list[dict],
        prompt_template: str | None = None,
    ) -> str:
        context = "\n\n".join(
            [f"Source: {chunk['source']}\n{chunk['chunk_text']}" for chunk in context_chunks]
        )
        system_prompt = (
            "You are a professional call-center support chatbot. "
            "You must answer strictly and only from the provided PDF context snippets. "
            "If the answer is missing in context, reply exactly: "
            "'I can only answer from the provided PDF documents.'"
        )
        if prompt_template:
            system_prompt = f"{system_prompt}\n\nPrompt template:\n{prompt_template}"

        messages = [{"role": "system", "content": system_prompt}]
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append(
            {
                "role": "user",
                "content": (
                    "Context:\n"
                    f"{context if context else 'No relevant context found.'}\n\n"
                    "Important: answer only from context sourced from PDF documents.\n\n"
                    "Customer question:\n"
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
