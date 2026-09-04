import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setOk(false);
    setLoading(true);
    try {
      await apiFetch("/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      setOk(true);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-md rounded-2xl border border-slate-800 bg-slate-900/60 p-8 shadow-xl">
      <h1 className="text-2xl font-semibold text-white">Forgot password</h1>
      <p className="mt-2 text-sm text-slate-400">
        Enter the <strong className="text-slate-300">exact</strong> email you use for{" "}
        <strong className="text-slate-300">unified sign-in</strong> (company workspace or platform admin). If that
        account exists, the server sends a reset link via <strong className="text-slate-300">Resend</strong> or{" "}
        <strong className="text-slate-300">SMTP</strong> when configured: set{" "}
        <code className="text-xs text-slate-500">RESEND_API_KEY</code> and{" "}
        <code className="text-xs text-slate-500">EMAIL_FROM</code>, or SMTP host/port and{" "}
        <code className="text-xs text-slate-500">EMAIL_FROM</code>.
      </p>
      <form className="mt-8 space-y-4" onSubmit={onSubmit}>
        <div>
          <label className="block text-xs font-medium text-slate-400">Email</label>
          <input
            type="email"
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none ring-brand-600 focus:ring-2"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
          />
        </div>
        {err && <p className="text-sm text-red-400">{err}</p>}
        {ok && (
          <p className="text-sm text-green-400">
            If an account exists for that email, you will receive instructions shortly. Check spam/junk. If nothing
            arrives, the address may not be registered for this workspace, or the sender may need a verified domain in
            Resend (or working SMTP).
          </p>
        )}
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-brand-600 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60"
        >
          {loading ? "Sending…" : "Send reset link"}
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
