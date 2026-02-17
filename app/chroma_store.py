import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import chromadb
from chromadb.api.models.Collection import Collection

from app.config import settings


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dummy_embedding() -> list[float]:
    return [0.0, 0.0, 0.0]


class ChromaStore:
    def __init__(self):
        persist_path = Path(settings.chroma_persist_directory)
        persist_path.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(path=str(persist_path))
        self.users = self.client.get_or_create_collection(name=settings.chroma_users_collection)
        self.chats = self.client.get_or_create_collection(name=settings.chroma_chats_collection)
        self.messages = self.client.get_or_create_collection(name=settings.chroma_messages_collection)
        self.documents = self.client.get_or_create_collection(name=settings.chroma_documents_collection)
        self.prompt_templates = self.client.get_or_create_collection(
            name=settings.chroma_prompt_templates_collection
        )

    def seed_prompt_templates(self):
        templates = [
            {
                "id": "persona_professional",
                "name": "Professional Agent",
                "template": (
                    "Use a formal and professional call-center tone. "
                    "Give clear, policy-aligned answers from retrieved PDF context only. "
                    "Do not add information outside the PDFs."
                ),
            },
            {
                "id": "persona_empathetic",
                "name": "Empathetic Agent",
                "template": (
                    "Respond with empathy and reassurance like a customer-care specialist. "
                    "Acknowledge customer concern first, then provide steps from retrieved PDF context only. "
                    "Do not add information outside the PDFs."
                ),
            },
            {
                "id": "persona_resolution",
                "name": "Resolution Agent",
                "template": (
                    "Focus on fast resolution. Give short step-by-step actions with numbered points. "
                    "Use retrieved PDF context only and avoid extra assumptions."
                ),
            },
        ]

        existing = self.prompt_templates.get(include=[])
        existing_ids = existing.get("ids") or []
        if existing_ids:
            self.prompt_templates.delete(ids=existing_ids)

        self.prompt_templates.add(
            ids=[item["id"] for item in templates],
            documents=[item["template"] for item in templates],
            metadatas=[{"name": item["name"], "created_at": _now_iso()} for item in templates],
            embeddings=[_dummy_embedding() for _ in templates],
        )

    def list_prompt_templates(self) -> list[dict]:
        data = self.prompt_templates.get(include=["documents", "metadatas"])
        ids = data.get("ids") or []
        docs = data.get("documents") or []
        metadatas = data.get("metadatas") or []

        result = []
        for template_id, doc, metadata in zip(ids, docs, metadatas):
            result.append(
                {
                    "id": template_id,
                    "name": (metadata or {}).get("name", "Template"),
                    "template": doc or "",
                }
            )
        return result

    def get_prompt_template(self, template_id: str | None) -> dict | None:
        if not template_id:
            return None
        data = self.prompt_templates.get(ids=[template_id], include=["documents", "metadatas"])
        ids = data.get("ids") or []
        if not ids:
            return None

        metadata = (data.get("metadatas") or [{}])[0] or {}
        document = (data.get("documents") or [""])[0] or ""
        return {"id": template_id, "name": metadata.get("name", "Template"), "template": document}

    def create_user(self, username: str, password_hash: str, full_name: str | None = None) -> dict:
        existing = self.get_user_by_username(username)
        if existing:
            return existing

        user_id = str(uuid4())
        payload = {
            "id": user_id,
            "username": username,
            "password_hash": password_hash,
            "full_name": full_name,
            "created_at": _now_iso(),
        }
        self.users.add(
            ids=[user_id],
            documents=[json.dumps(payload)],
            metadatas=[{"username": username}],
            embeddings=[_dummy_embedding()],
        )
        return payload

    def update_user_password(self, username: str, password_hash: str) -> bool:
        user = self.get_user_by_username(username)
        if not user:
            return False

        user["password_hash"] = password_hash
        self.users.update(
            ids=[user["id"]],
            documents=[json.dumps(user)],
            metadatas=[{"username": user["username"]}],
            embeddings=[_dummy_embedding()],
        )
        return True

    def get_user_by_username(self, username: str) -> dict | None:
        data = self.users.get(where={"username": username}, include=["documents"])
        ids = data.get("ids") or []
        if not ids:
            return None
        doc = (data.get("documents") or ["{}"])[0]
        return json.loads(doc)

    def get_user_by_id(self, user_id: str) -> dict | None:
        data = self.users.get(ids=[user_id], include=["documents"])
        ids = data.get("ids") or []
        if not ids:
            return None
        doc = (data.get("documents") or ["{}"])[0]
        return json.loads(doc)

    def list_chats(self, user_id: str) -> list[dict]:
        data = self.chats.get(where={"user_id": user_id}, include=["documents"])
        chats = [json.loads(doc) for doc in (data.get("documents") or [])]
        chats.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return chats

    def create_chat(self, user_id: str, title: str = "New Chat") -> dict:
        chat_id = str(uuid4())
        now = _now_iso()
        payload = {
            "id": chat_id,
            "user_id": user_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
        }
        self.chats.add(
            ids=[chat_id],
            documents=[json.dumps(payload)],
            metadatas=[{"user_id": user_id}],
            embeddings=[_dummy_embedding()],
        )
        return payload

    def get_chat(self, chat_id: str) -> dict | None:
        data = self.chats.get(ids=[chat_id], include=["documents"])
        ids = data.get("ids") or []
        if not ids:
            return None
        return json.loads((data.get("documents") or ["{}"])[0])

    def update_chat(self, chat: dict):
        self.chats.update(
            ids=[chat["id"]],
            documents=[json.dumps(chat)],
            metadatas=[{"user_id": chat["user_id"]}],
            embeddings=[_dummy_embedding()],
        )

    def add_message(
        self,
        chat_id: str,
        user_id: str,
        role: str,
        content: str,
        prompt_template_id: str | None = None,
        sources: list[str] | None = None,
    ) -> dict:
        message_id = str(uuid4())
        payload = {
            "id": message_id,
            "chat_id": chat_id,
            "user_id": user_id,
            "role": role,
            "content": content,
            "prompt_template_id": prompt_template_id,
            "sources": sources or [],
            "created_at": _now_iso(),
        }
        self.messages.add(
            ids=[message_id],
            documents=[json.dumps(payload)],
            metadatas=[{"chat_id": chat_id, "user_id": user_id, "role": role}],
            embeddings=[_dummy_embedding()],
        )

        chat = self.get_chat(chat_id)
        if chat:
            chat["updated_at"] = _now_iso()
            if chat.get("title") == "New Chat" and role == "user":
                chat["title"] = (content[:60] + "...") if len(content) > 60 else content
            self.update_chat(chat)

        return payload

    def list_messages(self, chat_id: str) -> list[dict]:
        data = self.messages.get(where={"chat_id": chat_id}, include=["documents"])
        messages = [json.loads(doc) for doc in (data.get("documents") or [])]
        messages.sort(key=lambda item: item.get("created_at", ""))
        return messages

    def clear_documents(self):
        existing = self.documents.get(include=[])
        ids = existing.get("ids") or []
        if ids:
            self.documents.delete(ids=ids)

    def add_document_chunk(self, source: str, chunk_text: str, embedding: list[float]):
        self.documents.add(
            ids=[str(uuid4())],
            documents=[chunk_text],
            metadatas=[{"source": source}],
            embeddings=[embedding],
        )

    def query_document_chunks(self, query_embedding: list[float], top_k: int) -> list[dict]:
        result = self.documents.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        items = []
        for doc, metadata, distance in zip(documents, metadatas, distances):
            items.append(
                {
                    "source": (metadata or {}).get("source", "unknown.pdf"),
                    "chunk_text": doc,
                    "distance": float(distance) if distance is not None else None,
                }
            )
        return items


store = ChromaStore()
