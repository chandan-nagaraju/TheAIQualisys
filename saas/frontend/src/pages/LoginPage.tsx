import { FormEvent, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { apiFetch, setWorkspaceCustomerId } from "../api";

export default function LoginPage() {
  const nav = useNavigate();
  const loc = useLocation();
  const redirectTo = (loc.state as { from?: string } | null)?.from || "/dashboard";
  const isAdminTarget = redirectTo.startsWith("/admin");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setLoading(true);
    try {
      const res = await apiFetch<{ access_token: string; role: string }>("/auth/unified-login", {
        method: "POST",
        body: JSON.stringify({ identifier, password }),
      });
      if (res.role === "platform_admin") {
        localStorage.removeItem("fir_token");
        setWorkspaceCustomerId(null);
        localStorage.setItem("fir_admin_token", res.access_token);
        nav(isAdminTarget ? redirectTo : "/admin");
        return;
      }
      localStorage.removeItem("fir_admin_token");
      localStorage.setItem("fir_token", res.access_token);
      nav(redirectTo);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-md rounded-2xl border border-slate-800 bg-slate-900/60 p-8 shadow-xl">
      <h1 className="text-2xl font-semibold text-white">Welcome back</h1>
      <p className="mt-2 text-sm text-slate-400">
        <strong className="text-slate-300">Company:</strong> email or vendor code.{" "}
        <strong className="text-slate-300">Platform admin:</strong> your admin email (same form).
      </p>
      <form className="mt-8 space-y-4" onSubmit={onSubmit}>
        <div>
          <label className="block text-xs font-medium text-slate-400">Email or vendor code</label>
          <input
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none ring-brand-600 focus:ring-2"
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
            required
            autoComplete="username"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-400">Password</label>
          <input
            type="password"
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none ring-brand-600 focus:ring-2"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
          />
        </div>
        {err && <p className="text-sm text-red-400">{err}</p>}
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-brand-600 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60"
        >
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <p className="mt-4 text-center text-sm">
        <Link className="text-slate-400 hover:text-brand-500 hover:underline" to="/forgot-password">
          Forgot password?
        </Link>
      </p>
      <p className="mt-6 text-center text-sm text-slate-400">
        New here?{" "}
        <Link className="text-brand-600 hover:underline" to="/signup">
          Create an account
        </Link>
      </p>
    </div>
  );
}
