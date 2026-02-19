# Function Call Flow Guide (Step-by-Step)

This document explains **which function triggers first** when you run this project, and how execution moves to the next functions across backend, frontend, ingestion, and evaluation.

---

## 1) When you run the backend (`uvicorn app.main:app ...`)

### 1.1 Import-time execution order (happens before first request)

1. Python imports `app.main`.
2. `app.main` imports `store` from `app.chroma_store`.
3. Importing `app.chroma_store` imports `settings` from `app.config`.
4. In `app.config`, `settings = Settings()` executes immediately.
   - Loads values from defaults + `.env` (`OPENAI_API_KEY`, model names, Chroma paths, etc.).
5. Back in `app.chroma_store`, global `store = ChromaStore()` executes immediately.
   - `ChromaStore.__init__()` runs.
   - Creates/open persistent path (`settings.chroma_persist_directory`).
   - Creates/opens collections: users, chats, messages, documents, prompt_templates.
6. `app.main` imports `RAGService` from `app.rag` and `verify_password` from `app.security`.
7. `app.main` creates FastAPI app:
   - `app = FastAPI(...)`
   - adds `SessionMiddleware`
   - configures templates + static mount.
8. `app.main` tries global initialization:
   - `rag_service = RAGService()`
   - `RAGService.__init__()` checks `settings.openai_api_key`.
   - If key missing, exception is caught and `rag_service = None`.

### 1.2 Startup event (runs once when server starts)

1. FastAPI calls `startup_event()`.
2. `startup_event()` calls `store.seed_prompt_templates()`.
3. `seed_prompt_templates()`:
   - clears existing template IDs from `prompt_templates`
   - inserts three personas (`persona_professional`, `persona_empathetic`, `persona_resolution`).

At this point server is ready.

---

## 2) Browser flow: first page load to authenticated chat

### 2.1 User opens `/`

1. Route handler `root(request)` executes.
2. Checks `request.session["user_id"]`.
3. If exists -> redirects to `/chat`; otherwise redirects to `/login`.

### 2.2 Login page (`/login`)

1. Route handler `login_page(request)` returns `templates/login.html`.
2. In browser, `login.html` loads `/static/login-react.js`.
3. Frontend bootstraps React:
   - `createRoot(...).render(<LoginApp />)`.

### 2.3 Submit login form

1. `LoginApp.onSubmit(event)` triggers.
2. Calls `fetch("/api/login", { method: "POST", body: formData })`.
3. Backend route `login(request, username, password)` executes.
4. `login()` calls `store.get_user_by_username(username)`.
5. `login()` calls `verify_password(password, user["password_hash"])`.
6. If valid:
   - sets `request.session["user_id"] = user["id"]`
   - returns `{ ok: true, username }`.
7. Frontend redirects browser to `/chat`.

---

## 3) Chat page initial load flow

### 3.1 Chat page render

1. Route handler `chat_page(request)` executes.
2. If no session user, redirect `/login`; else return `templates/chat.html`.
3. `chat.html` loads `/static/chat-react.js`.
4. React bootstraps `ChatApp`.

### 3.2 `ChatApp` first effects

On mount, first `useEffect` triggers:

1. `loadTemplates()` -> `GET /api/prompt-templates`
   - backend `list_prompt_templates(request)`
   - calls `get_current_user(request)`
   - then `store.list_prompt_templates()`.
2. `loadChats()` -> `GET /api/chats`
   - backend `list_chats(request)`
   - calls `get_current_user(request)`
   - then `store.list_chats(user_id)`.
3. If chats exist and no selected chat, frontend sets first `chat.id` as current.

Second `useEffect` depends on `currentChatId`:

4. `loadMessages(currentChatId)` -> `GET /api/chats/{chat_id}/messages`
   - backend `get_messages(chat_id, request)`
   - calls `get_current_user()`
   - calls `store.get_chat(chat_id)` and ownership check
   - calls `store.list_messages(chat_id)`.

---

## 4) Most important path: sending one chat message

When user clicks **Send**, this exact chain executes.

### 4.1 Frontend send flow

1. `ChatApp.sendMessage(event)` starts.
2. If no active chat, creates one:
   - `POST /api/chats`
   - backend `create_chat(request)`
   - `get_current_user()` -> `store.create_chat(user_id, "New Chat")`.
3. Adds optimistic user message in UI.
4. Calls `POST /api/chats/{chat_id}/messages` with JSON:
   - `{ message, prompt_template_id }`.

### 4.2 Backend message route flow

1. `send_message(chat_id, request)` starts.
2. Calls `get_current_user(request)`.
3. Parses JSON body and validates `message` non-empty.
4. If global `rag_service is None`, raises 500 (`OPENAI_API_KEY is not configured`).
5. Calls `store.get_chat(chat_id)` and verifies ownership.
6. Persists user message:
   - `store.add_message(... role="user" ...)`
   - inside `add_message()`:
     - inserts message
     - loads chat via `get_chat()`
     - updates chat `updated_at`
     - if title is `New Chat`, derives title from first user content
     - `update_chat(chat)`.
7. Loads full chat messages via `store.list_messages(chat_id)`.
8. Builds `history` from prior messages (`prior_messages[:-1]`).
9. Loads template via `store.get_prompt_template(prompt_template_id)`.
10. Embeds query:
    - `rag_service.embed_text(user_message)`
    - internally calls OpenAI embeddings API.
11. Retrieves relevant chunks:
    - `rag_service.find_relevant_chunks(query_embedding)`
    - internally `store.query_document_chunks(... top_k=settings.rag_top_k)`
    - Chroma similarity search returns top chunks.
12. Branch:
    - if no chunks -> assistant text is fallback:
      `I can only answer from the provided PDF documents.`
    - else -> generate answer:
      - `rag_service.generate_answer(...)`
      - builds system prompt + context + history
      - calls OpenAI chat completions API
      - returns assistant text.
13. Extract unique `sources` from retrieved chunks.
14. Persists assistant message:
    - `store.add_message(... role="assistant", sources=...)`.
15. Returns response payload with both user + assistant messages.

### 4.3 Frontend after response

1. Replaces optimistic message with server messages.
2. Shows assistant answer + sources.
3. Calls `loadChats()` again to refresh chat title/order.

---

## 5) Logout flow

1. Frontend `logout()` calls `POST /api/logout`.
2. Backend `logout(request)` executes `request.session.clear()`.
3. Frontend redirects to `/login`.

---

## 6) Data ingestion flow (`python -m scripts.ingest_data --data-dir data`)

### 6.1 Trigger order

1. Script entry reaches `if __name__ == "__main__":`.
2. Parses `--data-dir`.
3. Calls `ingest_directory(Path(args.data_dir).resolve())`.

### 6.2 Function chain in ingestion

1. `ingest_directory()` creates `rag = RAGService()`.
2. Calls `store.clear_documents()` to wipe existing vector chunks.
3. Finds all `.pdf` files recursively under data directory.
4. For each PDF:
   - `PdfReader(...)`
   - extract each page text
   - combine text
   - `split_text(text)` into overlapping chunks.
5. For each chunk:
   - `rag.embed_text(chunk)` (OpenAI embeddings)
   - `store.add_document_chunk(source, chunk_text, embedding)`.
6. Prints total indexed files/chunks.

---

## 7) Seed user flow (`python -m scripts.seed_user ...`)

1. Script parses CLI args.
2. Calls `seed_user(username, password, full_name, update_if_exists)`.
3. `seed_user()` calls `store.get_user_by_username(username)`.
4. Branch:
   - existing + no update -> prints already exists
   - existing + update -> `store.update_user_password(... hash_password(password))`
   - not existing -> `store.create_user(... hash_password(password), full_name)`.

---

## 8) Evaluation flow (`python -m scripts.evaluate_rag` OR Streamlit eval button)

### 8.1 CLI path

1. Script entry calls `evaluate_and_save()`.
2. `evaluate_and_save()` loads ground truth JSON.
3. Calls `store.seed_prompt_templates()`.
4. If document store empty -> `ingest_directory(Path("data").resolve())`.
5. Creates `rag_service = RAGService()`.
6. For each ground-truth question:
   - embed question (`embed_text`)
   - retrieve chunks (`find_relevant_chunks`)
   - answer (`generate_answer`) or fallback
   - compute metrics/latencies.
7. Aggregates 20 metrics.
8. Writes report JSON to `eval/rag_eval_report.json`.

### 8.2 Streamlit eval dashboard path (`streamlit_rag_eval_dashboard.py`)

1. Streamlit runs file top-to-bottom.
2. User clicks **Run RAG Evaluation** button.
3. Button handler calls `evaluate_and_save(...)`.
4. Then dashboard loads report JSON and renders cards/charts/tables.

---

## 9) Metrics dashboard flow (`streamlit_dashboard.py`)

1. Streamlit runs file top-to-bottom.
2. Executes `Base.metadata.create_all(bind=engine)`.
3. Opens DB session, queries `LogMetric` rows.
4. Converts rows -> DataFrame.
5. Computes latest metric by key.
6. Renders KPI cards, category bar chart, metrics table, and summary counts.

---

## 10) Quick “first function” summary by command

- `uvicorn app.main:app ...`
  - first meaningful triggers: import `app.main` -> import `app.config` (`settings = Settings()`) -> import `app.chroma_store` (`store = ChromaStore()`) -> `RAGService()` try-init -> startup `store.seed_prompt_templates()`.

- `python -m scripts.ingest_data --data-dir data`
  - first function: `ingest_directory(...)`.

- `python -m scripts.seed_user ...`
  - first function: `seed_user(...)`.

- `python -m scripts.seed_metrics`
  - first function: `seed_metrics(...)`.

- `python -m scripts.evaluate_rag`
  - first function: `evaluate_and_save(...)`.

- `streamlit run streamlit_dashboard.py`
  - first executed statements are top-level module statements in `streamlit_dashboard.py`.

- `streamlit run streamlit_rag_eval_dashboard.py`
  - first executed statements are top-level module statements in `streamlit_rag_eval_dashboard.py`.

---

## 11) Important notes about execution behavior

1. `store` is a **global singleton** created at import time in `app.chroma_store`.
2. `settings` is also a **global singleton** created at import time in `app.config`.
3. `rag_service` in `app.main` is initialized once at import; if API key missing then every send-message request returns 500 until restart with valid key.
4. Prompt templates are reseeded at backend startup and during evaluation.
5. Chat title changes from `New Chat` to first user message snippet when first user message is stored.

This is the end-to-end execution map for this repository.
