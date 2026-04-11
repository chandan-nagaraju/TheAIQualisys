import { useEffect, useState } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { apiUrl } from "../api";

type SubStatus = {
  enable_subscription: boolean;
  can_access_fir_workspace: boolean;
};

function authHeader(): HeadersInit {
  const t = localStorage.getItem("fir_token");
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export default function WorkspaceSubscriptionGate() {
  const [state, setState] = useState<"loading" | "ok" | "blocked">("loading");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(apiUrl("/subscription/status"), {
          headers: { "Content-Type": "application/json", ...authHeader() },
        });
        if (cancelled) return;
        if (res.status === 401) {
          setState("blocked");
          return;
        }
        if (!res.ok) {
          setState("blocked");
          return;
        }
        const s = (await res.json()) as SubStatus;
        if (cancelled) return;
        if (!s.enable_subscription || s.can_access_fir_workspace) setState("ok");
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
    return <Navigate to="/dashboard" replace state={{ workspaceBlocked: true }} />;
  }
  return <Outlet />;
}
