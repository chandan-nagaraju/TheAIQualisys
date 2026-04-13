import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiFetch } from "../api";

export default function SignupPage() {
  const nav = useNavigate();
  const [company_name, setCompanyName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [vendor_code, setVendorCode] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setLoading(true);
    try {
      const res = await apiFetch<{ access_token: string }>("/api/auth/signup", {
        method: "POST",
        body: JSON.stringify({ company_name, email, password, vendor_code }),
      });
      localStorage.setItem("fir_token", res.access_token);
      nav("/dashboard");
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Signup failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-md rounded-2xl border border-slate-800 bg-slate-900/60 p-8 shadow-xl">
      <h1 className="text-2xl font-semibold text-white">Create your company</h1>
      <p className="mt-2 text-sm text-slate-400">
        7-day free trial starts automatically. Already have an account?{" "}
        <Link className="text-brand-600 hover:underline" to="/login">
          Log in
        </Link>
      </p>
      <form className="mt-8 space-y-4" onSubmit={onSubmit}>
        <div>
          <label className="block text-xs font-medium text-slate-400">Company name</label>
          <input
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none ring-brand-600 focus:ring-2"
            value={company_name}
            onChange={(e) => setCompanyName(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-400">Email</label>
          <input
            type="email"
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none ring-brand-600 focus:ring-2"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-400">Vendor code (unique)</label>
          <input
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none ring-brand-600 focus:ring-2"
            value={vendor_code}
            onChange={(e) => setVendorCode(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-400">Password</label>
          <input
            type="password"
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none ring-brand-600 focus:ring-2"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
            required
          />
        </div>
        {err && <p className="text-sm text-red-400">{err}</p>}
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-brand-600 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60"
        >
          {loading ? "Creating…" : "Start free trial"}
        </button>
      </form>
    </div>
  );
}
