import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { setWorkspaceCustomerId } from "../api";
import { exitTenantImpersonation, isTenantImpersonation } from "../impersonation";
import ThemeSwitcher from "./ThemeSwitcher";
import { useTheme } from "../theme/ThemeContext";

/** Company shell routes where we show the platform-admin impersonation strip (not FIR workspace). */
function showImpersonationBannerPath(pathname: string): boolean {
  if (pathname === "/dashboard" || pathname === "/upgrade") return true;
  if (pathname.startsWith("/dashboard/")) return true;
  if (pathname.startsWith("/modules/")) return true;
  return false;
}

export default function Layout() {
  const loc = useLocation();
  const nav = useNavigate();
  const { theme } = useTheme();
  const [impersonating, setImpersonating] = useState(false);

  const companyTok = localStorage.getItem("fir_token");
  const adminTok = localStorage.getItem("fir_admin_token");
  const isAdminRoute = loc.pathname.startsWith("/admin");

  useEffect(() => {
    setImpersonating(isTenantImpersonation());
  }, [loc.pathname]);

  const showImpersonationStrip =
    impersonating && !!companyTok && !isAdminRoute && showImpersonationBannerPath(loc.pathname);

  const impersonationBannerCls =
    theme === "dark"
      ? "border-b border-amber-600/40 bg-amber-950/35 px-4 py-2 text-center text-sm text-amber-100"
      : theme === "grey"
        ? "border-b border-amber-300 bg-amber-50 px-4 py-2 text-center text-sm text-amber-950"
        : "border-b border-amber-300 bg-amber-50 px-4 py-2 text-center text-sm text-amber-950";

  const shell =
    theme === "light"
      ? "bg-slate-100"
      : theme === "grey"
        ? "bg-gradient-to-b from-zinc-200 via-zinc-100 to-zinc-200"
        : "bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950";

  const headerBar =
    theme === "light"
      ? "border-slate-200 bg-white/95 shadow-sm backdrop-blur"
      : theme === "grey"
        ? "border-zinc-300/90 bg-zinc-50/95 shadow-sm backdrop-blur"
        : "border-slate-800/80 bg-slate-950/80 backdrop-blur";

  const brand =
    theme === "light" ? "text-slate-900" : theme === "grey" ? "text-zinc-900" : "text-white";

  const navWrap =
    theme === "light"
      ? "rounded-lg border border-slate-200 bg-slate-50/90 p-2"
      : theme === "grey"
        ? "rounded-lg border border-zinc-300 bg-zinc-100/90 p-2"
        : "rounded-lg border border-slate-700/80 bg-slate-900/70 p-2";

  const navItemCls = ({ isActive }: { isActive: boolean }) => {
    if (theme === "light") {
      return `rounded-md px-3 py-2 text-sm font-medium ${isActive ? "bg-slate-800 text-white" : "text-slate-600 hover:bg-slate-200 hover:text-slate-900"}`;
    }
    if (theme === "grey") {
      return `rounded-md px-3 py-2 text-sm font-medium ${isActive ? "bg-zinc-700 text-white" : "text-zinc-600 hover:bg-zinc-300/80 hover:text-zinc-900"}`;
    }
    return `rounded-md px-3 py-2 text-sm font-medium ${isActive ? "bg-slate-800 text-white" : "text-slate-300 hover:bg-slate-800/80 hover:text-white"}`;
  };

  const logoutBtn =
    theme === "light"
      ? "rounded-md px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-50"
      : theme === "grey"
        ? "rounded-md px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-50"
        : "rounded-md px-3 py-2 text-sm font-medium text-red-400 hover:bg-slate-800";

  const footerBar =
    theme === "light"
      ? "border-slate-200 text-slate-500"
      : theme === "grey"
        ? "border-zinc-300 text-zinc-600"
        : "border-slate-800/80 text-slate-500";

  function logoutCompany() {
    if (isTenantImpersonation()) {
      exitTenantImpersonation(nav);
      setImpersonating(false);
      return;
    }
    localStorage.removeItem("fir_token");
    setWorkspaceCustomerId(null);
    nav("/login");
  }

  function logoutAdmin() {
    localStorage.removeItem("fir_admin_token");
    nav("/login");
  }

  return (
    <div className={`flex min-h-screen flex-col ${shell}`}>
      <header className={`border-b ${headerBar}`}>
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-3 px-3 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4 sm:px-4 sm:py-4">
          <div className="flex w-full min-w-0 items-center justify-between gap-3 sm:w-auto sm:flex-wrap sm:justify-start sm:gap-4">
            <Link
              to={isAdminRoute && adminTok ? "/admin" : "/"}
              className={`text-lg font-semibold tracking-tight ${brand}`}
            >
              TheAIQualisys
            </Link>
            <ThemeSwitcher />
          </div>
          <nav className={`flex w-full items-center gap-1 overflow-x-auto whitespace-nowrap pb-1 sm:w-auto sm:flex-wrap sm:overflow-visible sm:whitespace-normal sm:pb-0 ${navWrap}`}>
            {isAdminRoute && adminTok ? (
              <>
                <span className="px-2 text-xs uppercase tracking-wide text-amber-500/90">Platform admin</span>
                <NavLink end className={navItemCls} to="/admin">
                  All companies
                </NavLink>
                <NavLink className={navItemCls} to="/admin/users">
                  Users &amp; customers
                </NavLink>
                <NavLink className={navItemCls} to="/admin/pricing">
                  Pricing management
                </NavLink>
                <button type="button" className={logoutBtn} onClick={logoutAdmin}>
                  Log out
                </button>
              </>
            ) : companyTok ? (
              <>
                <NavLink end className={navItemCls} to="/">
                  Home
                </NavLink>
                <NavLink end className={navItemCls} to="/dashboard">
                  Dashboard
                </NavLink>
                <NavLink className={navItemCls} to="/dashboard/billing">
                  Usage &amp; billing
                </NavLink>
                <button type="button" className={logoutBtn} onClick={logoutCompany}>
                  Log out
                </button>
              </>
            ) : (
              <>
                <NavLink className={navItemCls} to="/pricing">
                  About
                </NavLink>
                <NavLink className={navItemCls} to="/pricing/all-modules">
                  Pricing
                </NavLink>
                <NavLink className={navItemCls} to="/login">
                  Login
                </NavLink>
                <NavLink className={navItemCls} to="/signup">
                  Sign up
                </NavLink>
              </>
            )}
          </nav>
        </div>
      </header>
      {showImpersonationStrip ? (
        <div className={impersonationBannerCls}>
          You are viewing this company as <strong>platform admin</strong>.{" "}
          <button
            type="button"
            className={`font-semibold underline ${theme === "dark" ? "text-amber-200" : "text-amber-900"}`}
            onClick={() => {
              exitTenantImpersonation(nav);
              setImpersonating(false);
            }}
          >
            Exit to admin
          </button>
        </div>
      ) : null}
      <main className="app-outlet mx-auto w-full max-w-6xl flex-1 px-3 py-6 sm:px-4 sm:py-8 lg:py-10">
        <Outlet />
      </main>
      <footer className={`border-t px-3 py-6 text-center text-xs sm:py-8 ${footerBar}`}>
        Developed by Chandan. Made with Cursor.ai.
      </footer>
    </div>
  );
}
