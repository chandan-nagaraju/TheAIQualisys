import { FormEvent, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { apiFetch } from "../api";

const MIN_PASSWORD_LEN = 8;

export default function ResetPasswordPage() {
  const [search] = useSearchParams();
  const nav = useNavigate();
  const token = useMemo(() => search.get("token") || "", [search]);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    if (!token) {
      setErr("Missing token in URL.");
      return;
    }
    if (password.length < MIN_PASSWORD_LEN) {
      setErr(`Password must be at least ${MIN_PASSWORD_LEN} characters.`);
      return;
    }
    if (password !== confirm) {
      setErr("Passwords do not match.");
      return;
    }
    setLoading(true);
    try {
      await apiFetch("/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({ token, new_password: password }),
      });
      nav("/login", { replace: true });
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Reset failed");
    } finally {
      setLoading(false);
    }
  }

  const tokenMissing = !token;

  return (
    <div className="mx-auto max-w-md rounded-2xl border border-slate-800 bg-slate-900/60 p-8 shadow-xl">
      <h1 className="text-2xl font-semibold text-white">Set new password</h1>
      <p className="mt-2 text-sm text-slate-400">Choose a new password for your account.</p>
      {tokenMissing && (
        <div className="mt-4 space-y-2 rounded-lg border border-red-900/60 bg-red-950/40 p-4 text-sm text-red-300">
          <p>This link is invalid, incomplete, or expired.</p>
          <p>
            <Link className="font-medium text-brand-400 hover:underline" to="/forgot-password">
              Request a new reset link
            </Link>
            {" · "}
            <Link className="text-slate-400 hover:text-brand-400 hover:underline" to="/login">
              Back to sign in
            </Link>
          </p>
        </div>
      )}
      <form className="mt-8 space-y-4" onSubmit={onSubmit}>
        <div>
          <label className="block text-xs font-medium text-slate-400">New password</label>
          <input
            type="password"
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none ring-brand-600 focus:ring-2"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={MIN_PASSWORD_LEN}
            autoComplete="new-password"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-400">Confirm password</label>
          <input
            type="password"
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none ring-brand-600 focus:ring-2"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            minLength={MIN_PASSWORD_LEN}
            autoComplete="new-password"
          />
        </div>
        {err && <p className="text-sm text-red-400">{err}</p>}
        <button
          type="submit"
          disabled={loading || tokenMissing}
          className="w-full rounded-lg bg-brand-600 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60"
        >
          {loading ? "Saving…" : "Update password"}
        </button>
      </form>
      <p className="mt-6 text-center text-sm text-slate-400">
        <Link className="text-brand-500 hover:underline" to="/login">
          Back to sign in
        </Link>
      </p>
    </div>
  );
}
