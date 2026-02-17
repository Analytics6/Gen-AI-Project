const form = document.getElementById("login-form");
const errorBox = document.getElementById("login-error");

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorBox.textContent = "";

  const formData = new FormData(form);
  const response = await fetch("/api/login", {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "Login failed" }));
    errorBox.textContent = payload.detail || "Login failed";
    return;
  }

  window.location.href = "/chat";
});
