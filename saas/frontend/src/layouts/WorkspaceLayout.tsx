import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { setWorkspaceCustomerId } from "../api";

export default function WorkspaceLayout() {
  const nav = useNavigate();
  const [impersonating, setImpersonating] = useState(false);

  useEffect(() => {
    setImpersonating(sessionStorage.getItem("fir_impersonating") === "1");
  }, []);

  function exitImpersonation() {
    const backup = sessionStorage.getItem("fir_admin_token_backup");
    if (backup) localStorage.setItem("fir_admin_token", backup);
    sessionStorage.removeItem("fir_admin_token_backup");
    sessionStorage.removeItem("fir_impersonating");
    localStorage.removeItem("fir_token");
    setWorkspaceCustomerId(null);
    setImpersonating(false);
    nav("/admin");
  }

  function logout() {
    if (sessionStorage.getItem("fir_impersonating") === "1") {
      exitImpersonation();
      return;
    }
    localStorage.removeItem("fir_token");
    setWorkspaceCustomerId(null);
    nav("/login");
  }

  const navCls = ({ isActive }: { isActive: boolean }) =>
    `rounded-md px-3 py-2 text-sm font-medium ${isActive ? "bg-slate-800 text-white" : "text-slate-600 hover:bg-slate-200"}`;

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <header className="border-b border-slate-200 bg-white shadow-sm">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <Link to="/workspace/dashboard" className="text-lg font-semibold text-slate-800">
            FIR Automation
          </Link>
          <nav className="flex flex-wrap items-center gap-1">
            <NavLink to="/dashboard" className={navCls}>
              QMS dashboard
            </NavLink>
            <NavLink to="/workspace/dashboard" className={navCls}>
              FIR workspace
            </NavLink>
            <NavLink to="/workspace/pricing" className={navCls}>
              FIR pricing
            </NavLink>
            <NavLink to="/dashboard/billing" className={navCls}>
              Usage &amp; billing
            </NavLink>
            <NavLink to="/upgrade" className={navCls}>
              Upgrade
            </NavLink>
            <NavLink to="/workspace/change-password" end className={navCls}>
              Change password
            </NavLink>
            <button
              type="button"
              onClick={logout}
              className="rounded-md px-3 py-2 text-sm text-red-700 hover:bg-red-50"
            >
              Log out
            </button>
          </nav>
        </div>
      </header>
      {impersonating && (
        <div className="border-b border-amber-300 bg-amber-50 px-4 py-2 text-center text-sm text-amber-950">
          You are viewing this workspace as <strong>platform admin</strong>.{" "}
          <button type="button" className="font-semibold text-amber-900 underline" onClick={() => exitImpersonation()}>
            Exit to admin
          </button>
        </div>
      )}
      <main className="mx-auto max-w-6xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  );
}
