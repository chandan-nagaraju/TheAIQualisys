import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { apiFetch, apiGet } from "../api";

type VerifyOk = { ok: boolean; company_name: string; email: string; vendor_code: string };

export default function SignupCompletePage() {
  const [sp] = useSearchParams();
  const nav = useNavigate();
  const token = sp.get("token")?.trim() ?? "";

  const [meta, setMeta] = useState<VerifyOk | null>(null);
  const [verifyErr, setVerifyErr] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitErr, setSubmitErr] = useState<string | null>(null);
  const [loadingVerify, setLoadingVerify] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!token) {
      setVerifyErr("Missing verification token. Open the link from your email.");
      setLoadingVerify(false);
      return;
    }
    let cancelled = false;
    (async () => {
      setLoadingVerify(true);
      setVerifyErr(null);
      try {
        const q = new URLSearchParams({ token });
        const data = await apiGet<VerifyOk>(`/auth/verify-signup?${q.toString()}`);
        if (!cancelled) setMeta(data);
      } catch (e) {
        if (!cancelled) setVerifyErr(e instanceof Error ? e.message : "Verification failed");
      } finally {
        if (!cancelled) setLoadingVerify(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitErr(null);
    if (!token) return;
    setSubmitting(true);
    try {
      const res = await apiFetch<{ ok: boolean; email: string }>("/auth/complete-signup", {
        method: "POST",
        body: JSON.stringify({
          token,
          password,
          confirm_password: confirmPassword,
        }),
      });
      const em = encodeURIComponent(res.email ?? "");
      nav(`/login?registered=1&email=${em}`);
    } catch (ex) {
      setSubmitErr(ex instanceof Error ? ex.message : "Could not create account");
    } finally {
      setSubmitting(false);
    }
  }

  if (loadingVerify) {
    return (
      <div className="mx-auto max-w-md rounded-2xl border border-slate-800 bg-slate-900/60 p-8 shadow-xl">
        <p className="text-slate-300">Verifying your email…</p>
      </div>
    );
  }

  if (verifyErr || !meta) {
    return (
      <div className="mx-auto max-w-md rounded-2xl border border-slate-800 bg-slate-900/60 p-8 shadow-xl">
        <h1 className="text-xl font-semibold text-white">Could not verify</h1>
        <p className="mt-2 text-sm text-red-400">{verifyErr}</p>
        <p className="mt-4 text-sm text-slate-400">
          <Link className="text-brand-600 hover:underline" to="/signup">
            Back to signup
          </Link>
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-md rounded-2xl border border-slate-800 bg-slate-900/60 p-8 shadow-xl">
      <h1 className="text-2xl font-semibold text-white">Complete your account</h1>
      <p className="mt-2 text-sm text-slate-400">
        <span className="text-slate-300">{meta.company_name}</span> — {meta.email}
      </p>
      <form className="mt-8 space-y-4" onSubmit={onSubmit}>
        <div>
          <label className="block text-xs font-medium text-slate-400">Password</label>
          <input
            type="password"
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none ring-brand-600 focus:ring-2"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
            required
            autoComplete="new-password"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-400">Confirm password</label>
          <input
            type="password"
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none ring-brand-600 focus:ring-2"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            minLength={8}
            required
            autoComplete="new-password"
          />
        </div>
        {submitErr && <p className="text-sm text-red-400">{submitErr}</p>}
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-brand-600 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60"
        >
          {submitting ? "Creating…" : "Create Account"}
        </button>
      </form>
    </div>
  );
}
