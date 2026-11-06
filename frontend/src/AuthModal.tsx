import { useState } from "react";
import { api, type AuthUser, errorText } from "./api";

interface Props {
  onAuth: (user: AuthUser) => void;
}

export function AuthModal({ onAuth }: Props) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      const res = mode === "register"
        ? await api.authRegister(email, name, password)
        : await api.authLogin(email, password);
      onAuth(res.user);
    } catch (e) {
      setErr(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-overlay" role="dialog" aria-modal="true" aria-label={mode === "login" ? "Sign in" : "Create account"}>
      <div className="auth-modal">
        {/* Wordmark */}
        <div className="auth-brand">
          <span className="cf-mark" aria-hidden="true">CF</span>
          <span className="auth-brand-name">Clariflow</span>
        </div>

        <h2 className="auth-title">
          {mode === "login" ? "Welcome back" : "Create your account"}
        </h2>
        <p className="auth-sub">
          {mode === "login"
            ? "Sign in to track your work orders and history."
            : "Start converting voice fault reports to verified work orders."}
        </p>

        {err && <div className="auth-error" role="alert">{err}</div>}

        <form onSubmit={submit} className="auth-form">
          {mode === "register" && (
            <div className="auth-field">
              <label htmlFor="auth-name">Your name</label>
              <input id="auth-name" type="text" value={name} onChange={e => setName(e.target.value)}
                placeholder="Amit Sharma" autoComplete="name" required />
            </div>
          )}
          <div className="auth-field">
            <label htmlFor="auth-email">Email address</label>
            <input id="auth-email" type="email" value={email} onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com" autoComplete="email" required />
          </div>
          <div className="auth-field">
            <label htmlFor="auth-pw">Password</label>
            <input id="auth-pw" type="password" value={password} onChange={e => setPassword(e.target.value)}
              placeholder={mode === "register" ? "Min. 6 characters" : "Your password"}
              autoComplete={mode === "register" ? "new-password" : "current-password"} required minLength={6} />
          </div>
          <button type="submit" className="btn primary big" disabled={busy}>
            {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>

        <p className="auth-switch">
          {mode === "login" ? (
            <>Don't have an account? <button type="button" className="link" onClick={() => { setMode("register"); setErr(""); }}>Sign up free</button></>
          ) : (
            <>Already have an account? <button type="button" className="link" onClick={() => { setMode("login"); setErr(""); }}>Sign in</button></>
          )}
        </p>

        <div className="auth-divider"><span>or</span></div>
        <p className="auth-guest-note">
          No account needed — you can <strong>use the app as a guest</strong>. Your work orders are saved locally.
        </p>
      </div>
    </div>
  );
}

