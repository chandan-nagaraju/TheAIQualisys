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
      ? "border-slate-200 bg-white shadow-sm"
      : theme === "grey"
        ? "border-zinc-300 bg-zinc-50 shadow-sm"
        : "border-slate-700 bg-slate-900 shadow-sm";

  const titleCls =
    theme === "light" ? "text-slate-800" : theme === "grey" ? "text-zinc-900" : "text-white";

  const navCls = ({ isActive }: { isActive: boolean }) => {
    if (theme === "light") {
      return `rounded-md px-3 py-2 text-sm font-medium ${isActive ? "bg-slate-800 text-white" : "text-slate-600 hover:bg-slate-200"}`;
    }
    if (theme === "grey") {
      return `rounded-md px-3 py-2 text-sm font-medium ${isActive ? "bg-zinc-700 text-white" : "text-zinc-600 hover:bg-zinc-300/80"}`;
    }
    return `rounded-md px-3 py-2 text-sm font-medium ${isActive ? "bg-slate-800 text-white" : "text-slate-400 hover:bg-slate-800/80"}`;
  };

  const logoutBtn =
    theme === "light"
      ? "rounded-md px-3 py-2 text-sm text-red-700 hover:bg-red-50"
      : theme === "grey"
        ? "rounded-md px-3 py-2 text-sm text-red-700 hover:bg-red-50"
        : "rounded-md px-3 py-2 text-sm text-red-400 hover:bg-slate-800";

  const footerBar =
    theme === "light"
      ? "border-slate-200 text-slate-500"
      : theme === "grey"
        ? "border-zinc-300 text-zinc-600"
        : "border-slate-700 text-slate-500";

  return (
    <div className={`flex min-h-screen flex-col ${shell}`}>
      <header className={`border-b ${headerBar}`}>
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex min-w-0 flex-wrap items-center gap-3">
            <Link to="/workspace/dashboard" className={`text-lg font-semibold ${titleCls}`}>
              FIR Automation
            </Link>
            <ThemeSwitcher />
          </div>
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
            <button type="button" onClick={logout} className={logoutBtn}>
              Log out
            </button>
          </nav>
        </div>
      </header>
      <main className="app-outlet mx-auto max-w-6xl flex-1 px-4 py-8">
        <Outlet />
      </main>
      <footer className={`mt-auto border-t py-8 text-center text-xs ${footerBar}`}>
        Developed by Chandan. Made with Cursor.ai.
      </footer>
    </div>
  );
}
