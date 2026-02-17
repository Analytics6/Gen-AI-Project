# Run Guide: Call Center Agent Chatbot (React + ChromaDB)

This guide runs the updated app with:

- **React UI** (login + chat)
- **ChromaDB** for users, chats, messages, prompt templates, and vector store
- **PDF-only retrieval** for chatbot answers

---

## 1) Prerequisites

- Python 3.11+
- `pip`
- (Azure mode only) ODBC Driver 18 for SQL Server and Azure SQL network access

---

## 2) Install dependencies

From the project root:

```bash
python3 -m pip install -r requirements.txt
```

---

## 3) Seed user in ChromaDB

```bash
python3 -m scripts.seed_user --username admin --password 'Admin@2026!' --full-name 'Admin User'
```

To rotate an existing password:

```bash
python3 -m scripts.seed_user --username admin --password 'Admin@2026!' --update-if-exists
```

---

## 4) Ingest PDF documents (required for answers)

Place your PDFs in `data/`, then run:

```bash
python3 -m scripts.ingest_data --data-dir data
```

Only `.pdf` files are indexed. If no relevant PDF context exists, the assistant replies with:

`I can only answer from the provided PDF documents.`

---

## 5) Start backend app

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

Open:
- `http://localhost:8001/login`

---

## 6) Optional: Streamlit metrics dashboard (legacy SQL metrics)

```bash
streamlit run streamlit_dashboard.py --server.port 8501 --server.address 0.0.0.0
```

Open:
- `http://localhost:8501`

---

## 5) Common issues

- **`uvicorn: command not found`**
  - Install dependencies: `python3 -m pip install -r requirements.txt`
- **`Address already in use`**
  - Change port, e.g. backend `--port 8001`
- **No chatbot answers beyond fallback message**
  - Ingest PDFs: `python3 -m scripts.ingest_data --data-dir data`
- **`OPENAI_API_KEY is not configured`**
  - Set `OPENAI_API_KEY` in `.env`

---

## 6) Stop running servers

In each terminal, press `Ctrl + C`.
