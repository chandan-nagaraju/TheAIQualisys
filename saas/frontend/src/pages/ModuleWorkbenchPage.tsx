import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiFetch } from "../api";
import { getModuleBySlug } from "../moduleCatalog";

type Session = {
  access: string;
  actions_remaining: number | null;
  days_remaining: number | null;
};

export default function ModuleWorkbenchPage() {
  const { slug } = useParams<{ slug: string }>();
  const nav = useNavigate();
  const def = slug ? getModuleBySlug(slug) : undefined;
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  const goPricing = useCallback(
    (msg?: string) => {
      if (!slug) return;
      nav(`/pricing/modules/${slug}`, {
        replace: true,
        state: { trialEnded: true, message: msg },
      });
    },
    [nav, slug],
  );

  const refreshSession = useCallback(async () => {
    if (!slug) return;
    try {
      const s = await apiFetch<Session>(`/api/modules/${slug}/session`, { method: "POST" });
      setSession(s);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      goPricing(msg || undefined);
    }
  }, [slug, goPricing]);

  useEffect(() => {
    if (!def || !slug) {
      setLoading(false);
      return;
    }
    (async () => {
      setLoading(true);
      await refreshSession();
      setLoading(false);
    })();
  }, [def, slug, refreshSession]);

  async function runDemoAction() {
    if (!slug) return;
    setActionMsg(null);
    try {
      const r = await apiFetch<Session & { ok: boolean }>(`/api/modules/${slug}/consume-action`, {
        method: "POST",
      });
      setSession({
        access: r.access,
        actions_remaining: r.actions_remaining,
        days_remaining: r.days_remaining,
      });
      setActionMsg("Action recorded.");
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      goPricing(msg || undefined);
    }
  }

  if (!def || !slug) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-8 text-center text-slate-400">
        Unknown module.{" "}
        <Link className="text-brand-500 hover:underline" to="/dashboard">
          Back to dashboard
        </Link>
      </div>
    );
  }

  if (loading || !session) {
    return <p className="text-slate-400">Opening module…</p>;
  }

  const limited = session.access === "trial";

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <Link to="/dashboard" className="text-sm font-medium text-brand-500 hover:underline">
            ← Module dashboard
          </Link>
          <h1 className="mt-2 text-2xl font-semibold text-white">{def.title}</h1>
          <p className="mt-1 text-sm text-slate-400">{def.shortDescription}</p>
        </div>
        <div className="rounded-xl border border-slate-700 bg-slate-900/60 px-4 py-3 text-sm text-slate-300">
          {session.access === "full" ? (
            <span className="font-medium text-emerald-400">Subscribed — full access</span>
          ) : (
            <>
              <span className="font-medium text-sky-400">Trial</span>
              {session.days_remaining != null && (
                <span className="ml-2 text-slate-400">{session.days_remaining} days left</span>
              )}
              {session.actions_remaining != null && (
                <span className="ml-2 text-slate-400">{session.actions_remaining} actions left</span>
              )}
            </>
          )}
        </div>
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-8">
        <p className="text-sm font-medium uppercase tracking-wide text-slate-500">Preview</p>
        <p className="mt-3 text-slate-300">
          This module is under active development. Use the action below to simulate work; each click uses one trial
          action (up to five during your trial window).
        </p>
        {limited && (
          <button
            type="button"
            onClick={() => runDemoAction()}
            className="mt-6 rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-brand-500"
          >
            Run sample workflow (uses 1 trial action)
          </button>
        )}
        {session.access === "full" && (
          <p className="mt-6 text-sm text-emerald-200/90">
            Full access — demo action counter is disabled. Production features will appear here as we ship.
          </p>
        )}
        {actionMsg && <p className="mt-4 text-sm text-emerald-400">{actionMsg}</p>}
      </div>

      <p className="text-center text-sm text-slate-500">
        Need more time?{" "}
        <Link className="font-medium text-brand-500 hover:underline" to={`/pricing/modules/${slug}`}>
          View pricing and enroll
        </Link>
      </p>
    </div>
  );
}
