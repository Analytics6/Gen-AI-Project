from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.db import Base, engine, get_db
from app.models import Chat, Message, User
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
    Base.metadata.create_all(bind=engine)


def get_current_user(request: Request, db: Session) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = db.query(User).filter(User.id == user_id).first()
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
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    request.session["user_id"] = user.id
    return {"ok": True, "username": user.username}


@app.post("/api/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/api/chats")
def list_chats(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    chats = (
        db.query(Chat)
        .filter(Chat.user_id == user.id)
        .order_by(Chat.updated_at.desc(), Chat.id.desc())
        .all()
    )
    return [
        {
            "id": c.id,
            "title": c.title,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }
        for c in chats
    ]


@app.post("/api/chats")
def create_chat(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    chat = Chat(user_id=user.id, title="New Chat")
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return {"id": chat.id, "title": chat.title}


@app.get("/api/chats/{chat_id}/messages")
def get_messages(chat_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    messages = (
        db.query(Message)
        .filter(Message.chat_id == chat_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ]


@app.post("/api/chats/{chat_id}/messages")
async def send_message(chat_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    data = await request.json()
    user_message = (data.get("message") or "").strip()

    if not user_message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if rag_service is None:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not configured")

    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    user_msg_row = Message(chat_id=chat_id, role="user", content=user_message)
    db.add(user_msg_row)
    db.commit()

    prior_messages = (
        db.query(Message)
        .filter(Message.chat_id == chat_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )

    history = [{"role": m.role, "content": m.content} for m in prior_messages[:-1]]
    query_embedding = rag_service.embed_text(user_message)
    context_chunks = rag_service.find_relevant_chunks(db, query_embedding)
    assistant_text = rag_service.generate_answer(user_message, context_chunks, history)

    assistant_msg_row = Message(chat_id=chat_id, role="assistant", content=assistant_text)
    db.add(assistant_msg_row)

    if chat.title == "New Chat":
        chat.title = (user_message[:60] + "...") if len(user_message) > 60 else user_message

    db.commit()

    return {
        "user_message": {"role": "user", "content": user_message},
        "assistant_message": {"role": "assistant", "content": assistant_text},
    }
