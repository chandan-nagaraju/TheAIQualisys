import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { setWorkspaceCustomerId } from "../api";
import ThemeSwitcher from "../components/ThemeSwitcher";
import { exitTenantImpersonation, isTenantImpersonation } from "../impersonation";
import { useTheme } from "../theme/ThemeContext";

export default function WorkspaceLayout() {
  const nav = useNavigate();
  const { theme } = useTheme();

  function logout() {
    if (isTenantImpersonation()) {
      exitTenantImpersonation(nav);
      return;
    }
    localStorage.removeItem("fir_token");
    setWorkspaceCustomerId(null);
    nav("/login");
  }

  const shell =
    theme === "light"
      ? "min-h-screen bg-slate-100 text-slate-900"
      : theme === "grey"
        ? "min-h-screen bg-zinc-200 text-zinc-900"
        : "min-h-screen bg-slate-950 text-slate-100";

  const headerBar =
    theme === "light"
      ? "border-slate-200 bg-white/95 shadow-sm backdrop-blur"
      : theme === "grey"
        ? "border-zinc-300 bg-zinc-50/95 shadow-sm backdrop-blur"
        : "border-slate-700 bg-slate-900/90 shadow-sm backdrop-blur";

  const titleCls =
    theme === "light" ? "text-slate-800" : theme === "grey" ? "text-zinc-900" : "text-white";

  const navCls = ({ isActive }: { isActive: boolean }) => {
    if (theme === "light") {
      return `inline-flex min-h-10 items-center rounded-md px-3 py-2 text-sm font-medium ${isActive ? "bg-slate-800 text-white" : "text-slate-600 hover:bg-slate-200"}`;
    }
    if (theme === "grey") {
      return `inline-flex min-h-10 items-center rounded-md px-3 py-2 text-sm font-medium ${isActive ? "bg-zinc-700 text-white" : "text-zinc-600 hover:bg-zinc-300/80"}`;
    }
    return `inline-flex min-h-10 items-center rounded-md px-3 py-2 text-sm font-medium ${isActive ? "bg-slate-800 text-white" : "text-slate-400 hover:bg-slate-800/80"}`;
  };

  const logoutBtn =
    theme === "light"
      ? "inline-flex min-h-10 items-center rounded-md px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-50"
      : theme === "grey"
        ? "inline-flex min-h-10 items-center rounded-md px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-50"
        : "inline-flex min-h-10 items-center rounded-md px-3 py-2 text-sm font-medium text-red-400 hover:bg-slate-800";

  const footerBar =
    theme === "light"
      ? "border-slate-200 text-slate-500"
      : theme === "grey"
        ? "border-zinc-300 text-zinc-600"
        : "border-slate-700 text-slate-500";

  const navWrap =
    theme === "light"
      ? "rounded-lg border border-slate-200 bg-slate-50/90 p-2"
      : theme === "grey"
        ? "rounded-lg border border-zinc-300 bg-zinc-100/90 p-2"
        : "rounded-lg border border-slate-700/80 bg-slate-900/70 p-2";

  return (
    <div className={`flex min-h-screen flex-col ${shell}`}>
      <header className={`border-b ${headerBar}`}>
        <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center justify-between gap-3 px-3 py-3 sm:px-4">
          <div className="flex min-w-0 flex-wrap items-center gap-3">
            <Link to="/workspace/dashboard" className={`text-lg font-semibold ${titleCls}`}>
              FIR Automation
            </Link>
            <ThemeSwitcher />
          </div>
          <nav className={`flex w-full flex-wrap items-stretch justify-start gap-1 md:w-auto ${navWrap}`}>
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
            <button type="button" onClick={logout} className={logoutBtn}>
              Log out
            </button>
          </nav>
        </div>
      </header>
      <main className="app-outlet mx-auto w-full max-w-7xl flex-1 px-3 py-6 sm:px-4 sm:py-8 lg:px-6">
        <Outlet />
      </main>
      <footer className={`mt-auto border-t py-8 text-center text-xs ${footerBar}`}>
        Developed by Chandan. Made with Cursor.ai.
      </footer>
    </div>
  );
}
