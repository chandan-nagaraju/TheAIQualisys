import { useEffect, useState } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { apiUrl } from "../api";

type SubStatus = {
  trial_active: boolean;
  subscription_active: boolean;
};

/** Avoid a full-page “Checking subscription…” wait on every in-workspace navigation. */
const SUB_CACHE_KEY = "fir_workspace_sub_v1";
const SUB_CACHE_TTL_MS = 120_000;

function authHeader(): HeadersInit {
  const t = localStorage.getItem("fir_token");
  return t ? { Authorization: `Bearer ${t}` } : {};
}

function tokenSuffix(): string {
  const t = localStorage.getItem("fir_token") || "";
  return t.slice(-16);
}

function readCachedOk(): boolean {
  if (typeof sessionStorage === "undefined") return false;
  try {
    const raw = sessionStorage.getItem(SUB_CACHE_KEY);
    if (!raw) return false;
    const { at, ok, suffix } = JSON.parse(raw) as { at: number; ok: boolean; suffix: string };
    if (suffix !== tokenSuffix()) return false;
    if (Date.now() - at > SUB_CACHE_TTL_MS) return false;
    return ok === true;
  } catch {
    return false;
  }
}

function writeSubCache(ok: boolean) {
  try {
    sessionStorage.setItem(
      SUB_CACHE_KEY,
      JSON.stringify({ at: Date.now(), ok, suffix: tokenSuffix() }),
    );
  } catch {
    /* quota / private mode */
  }
}

function clearSubCache() {
  try {
    sessionStorage.removeItem(SUB_CACHE_KEY);
  } catch {
    /* ignore */
  }
}

export default function WorkspaceSubscriptionGate() {
  const [state, setState] = useState<"loading" | "ok" | "blocked">(() =>
    readCachedOk() ? "ok" : "loading",
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(apiUrl("/subscription/status"), {
          headers: { "Content-Type": "application/json", ...authHeader() },
        });
        if (cancelled) return;
        if (res.status === 401) {
          clearSubCache();
          setState("blocked");
          return;
        }
        if (!res.ok) {
          clearSubCache();
          setState("blocked");
          return;
        }
        const s = (await res.json()) as SubStatus;
        if (cancelled) return;
        const okSub = s.trial_active || s.subscription_active;
        writeSubCache(okSub);
        if (okSub) setState("ok");
        else setState("blocked");
      } catch {
        if (!cancelled) setState("blocked");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (state === "loading") {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-slate-600 shadow-sm">
        Checking subscription…
      </div>
    );
  }
  if (state === "blocked") {
    return <Navigate to="/workspace/pricing" replace state={{ workspaceBlocked: true }} />;
  }
  return <Outlet />;
}
