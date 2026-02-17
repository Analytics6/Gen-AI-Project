import React, { useState } from "https://esm.sh/react@18.3.1";
import { createRoot } from "https://esm.sh/react-dom@18.3.1/client";
import htm from "https://esm.sh/htm@3.1.1";

const html = htm.bind(React.createElement);

function LoginApp() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const onSubmit = async (event) => {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      const formData = new FormData();
      formData.append("username", username);
      formData.append("password", password);

      const response = await fetch("/api/login", { method: "POST", body: formData });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({ detail: "Login failed" }));
        setError(payload.detail || "Login failed");
        return;
      }

      window.location.href = "/chat";
    } catch {
      setError("Unable to reach server");
    } finally {
      setLoading(false);
    }
  };

  return html`
    <main className="auth-wrapper">
      <section className="auth-card">
        <p className="auth-chip">Call Center Agent</p>
        <h1>Secure Sign In</h1>
        <p className="auth-subtext">Log in to access PDF-grounded support conversations.</p>

        <form className="auth-form" onSubmit=${onSubmit}>
          <label>
            Username
            <input
              type="text"
              value=${username}
              onInput=${(event) => setUsername(event.target.value)}
              required
            />
          </label>

          <label>
            Password
            <input
              type="password"
              value=${password}
              onInput=${(event) => setPassword(event.target.value)}
              required
            />
          </label>

          <button type="submit" disabled=${loading}>${loading ? "Signing in..." : "Sign in"}</button>
          <p className="error">${error}</p>
        </form>
      </section>
    </main>
  `;
}

const rootElement = document.getElementById("login-app");
if (rootElement) {
  createRoot(rootElement).render(html`<${LoginApp} />`);
}
