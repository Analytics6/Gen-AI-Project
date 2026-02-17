import React, { useEffect, useMemo, useState } from "https://esm.sh/react@18.3.1";
import { createRoot } from "https://esm.sh/react-dom@18.3.1/client";
import htm from "https://esm.sh/htm@3.1.1";

const html = htm.bind(React.createElement);

function MessageBubble({ role, content, sources }) {
  return html`
    <div className=${`message ${role}`}>
      <div className="message-role">${role === "assistant" ? "Agent" : "You"}</div>
      <div>${content}</div>
      ${role === "assistant" && sources?.length
        ? html`<div className="message-sources">Sources: ${sources.join(", ")}</div>`
        : null}
    </div>
  `;
}

function ChatApp() {
  const [chats, setChats] = useState([]);
  const [currentChatId, setCurrentChatId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [templates, setTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  const templateOptions = useMemo(() => [{ id: "", name: "Default" }, ...templates], [templates]);

  const loadTemplates = async () => {
    const response = await fetch("/api/prompt-templates");
    if (response.status === 401) {
      window.location.href = "/login";
      return;
    }
    const data = await response.json();
    setTemplates(data);
  };

  const loadChats = async () => {
    const response = await fetch("/api/chats");
    if (response.status === 401) {
      window.location.href = "/login";
      return;
    }

    const data = await response.json();
    setChats(data);

    if (!currentChatId && data.length > 0) {
      setCurrentChatId(data[0].id);
    }
  };

  const loadMessages = async (chatId) => {
    if (!chatId) {
      setMessages([]);
      return;
    }
    const response = await fetch(`/api/chats/${chatId}/messages`);
    const data = await response.json();
    setMessages(data);
  };

  const createChat = async () => {
    const response = await fetch("/api/chats", { method: "POST" });
    const chat = await response.json();
    await loadChats();
    setCurrentChatId(chat.id);
    setMessages([]);
  };

  const sendMessage = async (event) => {
    event.preventDefault();
    const text = input.trim();
    if (!text || sending) {
      return;
    }

    setSending(true);
    setError("");

    let chatId = currentChatId;
    if (!chatId) {
      const response = await fetch("/api/chats", { method: "POST" });
      const chat = await response.json();
      chatId = chat.id;
      setCurrentChatId(chat.id);
      await loadChats();
    }

    const optimisticUserMessage = {
      id: `tmp-${Date.now()}`,
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
      sources: [],
    };

    setMessages((prev) => [...prev, optimisticUserMessage]);
    setInput("");

    const response = await fetch(`/api/chats/${chatId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        prompt_template_id: selectedTemplate || null,
      }),
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({ detail: "Failed to send message" }));
      setError(payload.detail || "Failed to send message");
      setMessages((prev) => prev.filter((item) => item.id !== optimisticUserMessage.id));
      setSending(false);
      return;
    }

    const payload = await response.json();
    setMessages((prev) => [
      ...prev.filter((item) => item.id !== optimisticUserMessage.id),
      {
        id: `u-${Date.now()}`,
        role: "user",
        content: payload.user_message.content,
        sources: [],
      },
      {
        id: `a-${Date.now()}`,
        role: "assistant",
        content: payload.assistant_message.content,
        sources: payload.assistant_message.sources || [],
      },
    ]);

    await loadChats();
    setSending(false);
  };

  const logout = async () => {
    await fetch("/api/logout", { method: "POST" });
    window.location.href = "/login";
  };

  useEffect(() => {
    loadTemplates();
    loadChats();
  }, []);

  useEffect(() => {
    loadMessages(currentChatId);
  }, [currentChatId]);

  return html`
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-top">
          <h2>Support Chats</h2>
          <button onClick=${createChat}>New Chat</button>
        </div>

        <div className="chat-list">
          ${chats.map(
            (chat) => html`
              <button
                key=${chat.id}
                className=${`chat-item ${chat.id === currentChatId ? "active" : ""}`}
                onClick=${() => setCurrentChatId(chat.id)}
              >
                <span>${chat.title}</span>
              </button>
            `
          )}
        </div>

        <button className="logout-btn" onClick=${logout}>Logout</button>
      </aside>

      <main className="chat-main">
        <header className="chat-toolbar">
          <div>
            <h1>Call Center Agent Chatbot</h1>
            <p>Answers are constrained to indexed PDF documents.</p>
          </div>
          <label className="template-picker">
            Prompt Template
            <select value=${selectedTemplate} onChange=${(event) => setSelectedTemplate(event.target.value)}>
              ${templateOptions.map(
                (template) => html`<option key=${template.id || "default"} value=${template.id}>${template.name}</option>`
              )}
            </select>
          </label>
        </header>

        <section className="messages">
          ${messages.length === 0
            ? html`<div className="empty-state">Start a chat to get PDF-grounded support answers.</div>`
            : messages.map(
                (message) =>
                  html`<${MessageBubble}
                    key=${message.id}
                    role=${message.role}
                    content=${message.content}
                    sources=${message.sources}
                  />`
              )}
        </section>

        <form className="message-form" onSubmit=${sendMessage}>
          <input
            type="text"
            value=${input}
            onInput=${(event) => setInput(event.target.value)}
            placeholder="Ask a customer support question from PDF docs..."
            required
          />
          <button type="submit" disabled=${sending}>${sending ? "Sending..." : "Send"}</button>
        </form>

        <p className="error">${error}</p>
      </main>
    </div>
  `;
}

const rootElement = document.getElementById("chat-app");
if (rootElement) {
  createRoot(rootElement).render(html`<${ChatApp} />`);
}
