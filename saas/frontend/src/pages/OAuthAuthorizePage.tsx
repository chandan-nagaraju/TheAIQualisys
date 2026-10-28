import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { apiFetch } from "../api";

type Preview = {
  client_id: string;
  client_name: string;
  redirect_uri: string;
  scope: string;
  state: string;
  code_challenge_method: string;
};

/**
 * Desktop OAuth consent UI.
 * Opened via GET /oauth/authorize → SPA redirect with PKCE params.
 * Never puts JWTs in the redirect; only an authorization code is returned to the desktop app.
 */
export default function OAuthAuthorizePage() {
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const [preview, setPreview] = useState<Preview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const params = useMemo(
    () => ({
      response_type: sp.get("response_type") || "code",
      client_id: sp.get("client_id") || "",
      redirect_uri: sp.get("redirect_uri") || "",
      scope: sp.get("scope") || "",
      state: sp.get("state") || "",
      code_challenge: sp.get("code_challenge") || "",
      code_challenge_method: sp.get("code_challenge_method") || "S256",
    }),
    [sp],
  );

  const queryString = useMemo(() => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v) q.set(k, v);
    });
    return q.toString();
  }, [params]);

  useEffect(() => {
    const token = localStorage.getItem("fir_token");
    if (!token) {
      nav("/login", { replace: true, state: { from: `/oauth/authorize?${queryString}` } });
      return;
    }
    if (localStorage.getItem("fir_admin_token")) {
      setErr("Platform admin sessions cannot authorize desktop clients. Sign in as a company user.");
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await apiFetch<Preview>(`/oauth/authorize/preview?${queryString}`);
        if (!cancelled) setPreview(res);
      } catch (ex) {
        if (!cancelled) {
          const msg = ex instanceof Error ? ex.message : "Authorization request invalid";
          if (/not authenticated|invalid token|401/i.test(msg)) {
            nav("/login", { replace: true, state: { from: `/oauth/authorize?${queryString}` } });
            return;
          }
          setErr(
            /access_denied|direct company login|impersonat/i.test(msg)
              ? "Desktop authorization requires signing in directly as the company user (admin impersonation cannot approve desktop access)."
              : msg
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [nav, queryString]);

  async function decide(decision: "approve" | "deny") {
    setBusy(true);
    setErr(null);
    try {
      const res = await apiFetch<{ redirect_to: string }>("/oauth/authorize/consent", {
        method: "POST",
        body: JSON.stringify({ ...params, decision }),
      });
      window.location.assign(res.redirect_to);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Consent failed");
      setBusy(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
  }

  return (
    <div className="mx-auto max-w-lg rounded-2xl border border-slate-800 bg-slate-900/70 p-8 shadow-xl">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-teal-400/90">TheAIQualisys</p>
      <h1 className="mt-3 text-2xl font-semibold text-white">Authorize desktop app</h1>
      <p className="mt-2 text-sm text-slate-400">
        A desktop application is requesting access to your company account for software licensing.
        Your password and access token are never placed in the app redirect URL.
      </p>

      {err && (
        <p className="mt-4 rounded-lg border border-rose-900/50 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
          {err}
        </p>
      )}

      {!err && !preview && <p className="mt-6 text-sm text-slate-400">Checking authorization request…</p>}

      {preview && (
        <form className="mt-6 space-y-4" onSubmit={onSubmit}>
          <div className="rounded-xl border border-slate-700/80 bg-slate-950/50 p-4">
            <p className="text-sm text-slate-400">Application</p>
            <p className="mt-1 text-lg font-medium text-white">{preview.client_name}</p>
            <p className="mt-3 text-sm text-slate-400">Requested access</p>
            <p className="mt-1 font-mono text-sm text-teal-200/90">{preview.scope}</p>
            <p className="mt-3 break-all text-xs text-slate-500">Redirect: {preview.redirect_uri}</p>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row">
            <button
              type="button"
              disabled={busy}
              onClick={() => void decide("approve")}
              className="flex-1 rounded-lg bg-teal-600 py-2.5 text-sm font-semibold text-white hover:bg-teal-500 disabled:opacity-60"
            >
              {busy ? "Working…" : "Allow QR Code Desktop"}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => void decide("deny")}
              className="flex-1 rounded-lg border border-slate-600 py-2.5 text-sm font-semibold text-slate-200 hover:bg-slate-800 disabled:opacity-60"
            >
              Deny
            </button>
          </div>
        </form>
      )}

      <p className="mt-6 text-center text-sm text-slate-500">
        Wrong account?{" "}
        <Link
          className="text-teal-400 hover:underline"
          to="/login"
          state={{ from: `/oauth/authorize?${queryString}` }}
        >
          Sign in again
        </Link>
      </p>
    </div>
  );
}
