import { useEffect, useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
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

  const navLink =
    theme === "light"
      ? "text-slate-600 hover:text-slate-900"
      : theme === "grey"
        ? "text-zinc-600 hover:text-zinc-900"
        : "text-slate-300 hover:text-white";

  const btnOutline =
    theme === "light"
      ? "rounded border border-slate-300 px-2 py-1 text-slate-700 hover:bg-slate-100"
      : theme === "grey"
        ? "rounded border border-zinc-400 px-2 py-1 text-zinc-800 hover:bg-zinc-200"
        : "rounded border border-slate-600 px-2 py-1 text-slate-200 hover:bg-slate-800";

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
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-4">
          <div className="flex min-w-0 flex-wrap items-center gap-3 sm:gap-4">
            <Link
              to={isAdminRoute && adminTok ? "/admin" : "/"}
              className={`text-lg font-semibold tracking-tight ${brand}`}
            >
              TheAIQualisys
            </Link>
            <ThemeSwitcher />
          </div>
          <nav className={`flex flex-wrap items-center gap-3 text-sm ${navLink}`}>
            {isAdminRoute && adminTok ? (
              <>
                <span className="text-xs uppercase tracking-wide text-amber-500/90">Platform admin</span>
                <Link className={navLink} to="/admin">
                  All companies
                </Link>
                <Link className={navLink} to="/admin/users">
                  Users &amp; customers
                </Link>
                <Link className={navLink} to="/admin/pricing">
                  Pricing management
                </Link>
                <button type="button" className={btnOutline} onClick={logoutAdmin}>
                  Log out
                </button>
              </>
            ) : companyTok ? (
              <>
                <Link className={navLink} to="/">
                  Home
                </Link>
                <Link className={navLink} to="/dashboard">
                  Dashboard
                </Link>
                <Link className={navLink} to="/dashboard/billing">
                  Usage &amp; billing
                </Link>
                <button type="button" className={btnOutline} onClick={logoutCompany}>
                  Log out
                </button>
              </>
            ) : (
              <>
                <Link className={navLink} to="/pricing">
                  About
                </Link>
                <Link className={navLink} to="/pricing/all-modules">
                  Pricing
                </Link>
                <Link className={navLink} to="/login">
                  Login
                </Link>
                <Link className={navLink} to="/signup">
                  Sign up
                </Link>
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
      <main className="app-outlet mx-auto w-full max-w-6xl flex-1 px-4 py-10">
        <Outlet />
      </main>
      <footer className={`border-t py-8 text-center text-xs ${footerBar}`}>
        Developed by Chandan. Made with Cursor.ai.
      </footer>
    </div>
  );
}
