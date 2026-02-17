const chatList = document.getElementById("chat-list");
const messagesBox = document.getElementById("messages");
const form = document.getElementById("message-form");
const input = document.getElementById("message-input");
const newChatBtn = document.getElementById("new-chat-btn");
const logoutBtn = document.getElementById("logout-btn");

let currentChatId = null;

function addMessage(role, content) {
  const div = document.createElement("div");
  div.className = `message ${role}`;
  div.textContent = content;
  messagesBox.appendChild(div);
  messagesBox.scrollTop = messagesBox.scrollHeight;
}

async function loadChats() {
  const response = await fetch("/api/chats");
  if (response.status === 401) {
    window.location.href = "/login";
    return;
  }

  const chats = await response.json();
  chatList.innerHTML = "";

  chats.forEach((chat) => {
    const item = document.createElement("div");
    item.className = `chat-item ${chat.id === currentChatId ? "active" : ""}`;
    item.textContent = chat.title;
    item.onclick = () => selectChat(chat.id);
    chatList.appendChild(item);
  });

  if (!currentChatId && chats.length > 0) {
    await selectChat(chats[0].id);
  }
}

async function selectChat(chatId) {
  currentChatId = chatId;
  await loadChats();

  const response = await fetch(`/api/chats/${chatId}/messages`);
  const messages = await response.json();
  messagesBox.innerHTML = "";
  messages.forEach((m) => addMessage(m.role, m.content));
}

async function createChat() {
  const response = await fetch("/api/chats", { method: "POST" });
  const chat = await response.json();
  currentChatId = chat.id;
  await loadChats();
  messagesBox.innerHTML = "";
}

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) {
    return;
  }

  if (!currentChatId) {
    await createChat();
  }

  addMessage("user", text);
  input.value = "";

  const response = await fetch(`/api/chats/${currentChatId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: text }),
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "Failed to send message" }));
    addMessage("assistant", `Error: ${payload.detail || "Failed to send message"}`);
    return;
  }

  const payload = await response.json();
  addMessage("assistant", payload.assistant_message.content);
  await loadChats();
});

newChatBtn?.addEventListener("click", createChat);

logoutBtn?.addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  window.location.href = "/login";
});

loadChats();
