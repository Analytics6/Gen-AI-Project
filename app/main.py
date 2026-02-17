from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.chroma_store import store
from app.config import settings
from app.rag import RAGService
from app.security import verify_password


app = FastAPI(title=settings.app_name)
app.add_middleware(SessionMiddleware, secret_key=settings.app_secret_key)

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

try:
    rag_service = RAGService()
except Exception:
    rag_service = None


@app.on_event("startup")
def startup_event():
    store.seed_prompt_templates()


def get_current_user(request: Request) -> dict:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    return user


@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse(url="/chat", status_code=302)
    return RedirectResponse(url="/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("chat.html", {"request": request})


@app.post("/api/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    user = store.get_user_by_username(username)
    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    request.session["user_id"] = user["id"]
    return {"ok": True, "username": user["username"]}


@app.post("/api/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/api/chats")
def list_chats(request: Request):
    user = get_current_user(request)
    chats = store.list_chats(user_id=user["id"])
    return [
        {
            "id": c["id"],
            "title": c["title"],
            "created_at": c.get("created_at"),
            "updated_at": c.get("updated_at"),
        }
        for c in chats
    ]


@app.post("/api/chats")
def create_chat(request: Request):
    user = get_current_user(request)
    chat = store.create_chat(user_id=user["id"], title="New Chat")
    return {"id": chat["id"], "title": chat["title"]}


@app.get("/api/chats/{chat_id}/messages")
def get_messages(chat_id: str, request: Request):
    user = get_current_user(request)
    chat = store.get_chat(chat_id)
    if not chat or chat.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Chat not found")

    messages = store.list_messages(chat_id=chat_id)
    return [
        {
            "id": m["id"],
            "role": m["role"],
            "content": m["content"],
            "created_at": m.get("created_at"),
            "sources": m.get("sources", []),
        }
        for m in messages
    ]


@app.post("/api/chats/{chat_id}/messages")
async def send_message(chat_id: str, request: Request):
    user = get_current_user(request)
    data = await request.json()
    user_message = (data.get("message") or "").strip()
    prompt_template_id = (data.get("prompt_template_id") or "").strip() or None

    if not user_message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if rag_service is None:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not configured")

    chat = store.get_chat(chat_id)
    if not chat or chat.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Chat not found")

    store.add_message(chat_id=chat_id, user_id=user["id"], role="user", content=user_message)
    prior_messages = store.list_messages(chat_id=chat_id)
    history = [{"role": m["role"], "content": m["content"]} for m in prior_messages[:-1]]

    prompt_template = store.get_prompt_template(prompt_template_id)
    query_embedding = rag_service.embed_text(user_message)
    context_chunks = rag_service.find_relevant_chunks(query_embedding)
    if not context_chunks:
        assistant_text = "I can only answer from the provided PDF documents."
    else:
        assistant_text = rag_service.generate_answer(
            user_message=user_message,
            context_chunks=context_chunks,
            history=history,
            prompt_template=prompt_template["template"] if prompt_template else None,
        )

    sources = sorted({item["source"] for item in context_chunks})
    store.add_message(
        chat_id=chat_id,
        user_id=user["id"],
        role="assistant",
        content=assistant_text,
        prompt_template_id=prompt_template_id,
        sources=sources,
    )

    return {
        "user_message": {"role": "user", "content": user_message},
        "assistant_message": {
            "role": "assistant",
            "content": assistant_text,
            "sources": sources,
        },
    }


@app.get("/api/prompt-templates")
def list_prompt_templates(request: Request):
    get_current_user(request)
    return store.list_prompt_templates()
