import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { apiFetch, setWorkspaceCustomerId } from "../api";
import { exitTenantImpersonation, isTenantImpersonation } from "../impersonation";
import { showCompanyShellBannerPath } from "../layout/companyShellBannerPaths";
import BrandLogo from "./BrandLogo";
import HeaderBackButton from "./HeaderBackButton";
import ThemeSwitcher from "./ThemeSwitcher";
import { useTheme } from "../theme/ThemeContext";

function formatDateShort(isoDate: string | null | undefined): string | null {
  if (!isoDate) return null;
  try {
    const d = new Date(`${isoDate}T12:00:00`);
    if (Number.isNaN(d.getTime())) return isoDate;
    return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return isoDate;
  }
}

function daysLabel(n: number) {
  return n === 1 ? "1 day" : `${n} days`;
}

type SubBanner =
  | {
      kind: "trial";
      daysLeft: number;
      trialEndsLabel: string | null;
      planType: string;
    }
  | {
      kind: "paid";
      daysLeft: number;
      subscriptionEndsLabel: string | null;
      planType: string;
    };

export default function Layout() {
  const loc = useLocation();
  const nav = useNavigate();
  const { theme } = useTheme();
  const [impersonating, setImpersonating] = useState(false);
  const [subBanner, setSubBanner] = useState<SubBanner | null>(null);

  const companyTok = localStorage.getItem("fir_token");
  const adminTok = localStorage.getItem("fir_admin_token");
  const isAdminRoute = loc.pathname.startsWith("/admin");
  const isLandingHome = loc.pathname === "/";

  useEffect(() => {
    setImpersonating(isTenantImpersonation());
  }, [loc.pathname]);

  useEffect(() => {
    let cancelled = false;
    const path = loc.pathname;
    if (
      !companyTok ||
      isAdminRoute ||
      !showCompanyShellBannerPath(path) ||
      isTenantImpersonation()
    ) {
      setSubBanner(null);
      return;
    }
    (async () => {
      try {
        const s = await apiFetch<{
          trial_active: boolean;
          trial_days_remaining: number | null;
          subscription_active: boolean;
          subscription_days_remaining: number | null;
          company: {
            plan_type: string;
            subscription_status: string;
            trial_end_date: string;
            subscription_end: string | null;
          };
        }>("/subscription/status");
        if (cancelled) return;

        if (s.trial_active && s.trial_days_remaining != null) {
          setSubBanner({
            kind: "trial",
            daysLeft: s.trial_days_remaining,
            trialEndsLabel: formatDateShort(s.company.trial_end_date),
            planType: s.company.plan_type,
          });
          return;
        }

        if (s.subscription_active && s.subscription_days_remaining != null) {
          setSubBanner({
            kind: "paid",
            daysLeft: s.subscription_days_remaining,
            subscriptionEndsLabel: formatDateShort(s.company.subscription_end),
            planType: s.company.plan_type,
          });
          return;
        }

        setSubBanner(null);
      } catch {
        if (!cancelled) setSubBanner(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loc.pathname, companyTok, isAdminRoute]);

  const showImpersonationStrip =
    impersonating && !!companyTok && !isAdminRoute && showCompanyShellBannerPath(loc.pathname);

  const showSubscriptionStrip =
    !showImpersonationStrip &&
    !!companyTok &&
    !isAdminRoute &&
    showCompanyShellBannerPath(loc.pathname) &&
    subBanner !== null;

  const impersonationBannerCls =
    theme === "dark"
      ? "border-b border-amber-600/40 bg-amber-950/35 px-4 py-2 text-center text-sm text-amber-100"
      : theme === "grey"
        ? "border-b border-amber-300 bg-amber-50 px-4 py-2 text-center text-sm text-amber-950"
        : "border-b border-amber-300 bg-amber-50 px-4 py-2 text-center text-sm text-amber-950";

  const trialBannerCls =
    theme === "dark"
      ? "border-b border-sky-600/35 bg-sky-950/30 px-4 py-2 text-center text-sm text-sky-100"
      : theme === "grey"
        ? "border-b border-sky-300 bg-sky-50 px-4 py-2 text-center text-sm text-sky-950"
        : "border-b border-sky-200 bg-sky-50 px-4 py-2 text-center text-sm text-sky-950";

  const paidBannerCls =
    theme === "dark"
      ? "border-b border-emerald-600/35 bg-emerald-950/25 px-4 py-2 text-center text-sm text-emerald-100"
      : theme === "grey"
        ? "border-b border-emerald-300 bg-emerald-50 px-4 py-2 text-center text-sm text-emerald-950"
        : "border-b border-emerald-200 bg-emerald-50 px-4 py-2 text-center text-sm text-emerald-950";

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
      ? "rounded-lg border border-slate-200 bg-slate-50/90 p-1"
      : theme === "grey"
        ? "rounded-lg border border-zinc-300 bg-zinc-100/90 p-1"
        : "rounded-lg border border-slate-700/80 bg-slate-900/70 p-1";

  const navItemCls = ({ isActive }: { isActive: boolean }) => {
    if (theme === "light") {
      return `inline-flex h-9 items-center whitespace-nowrap rounded-md px-3.5 text-sm font-medium leading-none ${isActive ? "bg-slate-800 text-white" : "text-slate-600 hover:bg-slate-200 hover:text-slate-900"}`;
    }
    if (theme === "grey") {
      return `inline-flex h-9 items-center whitespace-nowrap rounded-md px-3.5 text-sm font-medium leading-none ${isActive ? "bg-zinc-700 text-white" : "text-zinc-600 hover:bg-zinc-300/80 hover:text-zinc-900"}`;
    }
    return `inline-flex h-9 items-center whitespace-nowrap rounded-md px-3.5 text-sm font-medium leading-none ${isActive ? "bg-slate-800 text-white" : "text-slate-300 hover:bg-slate-800/80 hover:text-white"}`;
  };

  const logoutBtn =
    theme === "light"
      ? "inline-flex h-9 items-center whitespace-nowrap rounded-md px-3.5 text-sm font-medium leading-none text-red-700 hover:bg-red-50"
      : theme === "grey"
        ? "inline-flex h-9 items-center whitespace-nowrap rounded-md px-3.5 text-sm font-medium leading-none text-red-700 hover:bg-red-50"
        : "inline-flex h-9 items-center whitespace-nowrap rounded-md px-3.5 text-sm font-medium leading-none text-red-400 hover:bg-slate-800";

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

  const linkTrial = theme === "dark" ? "text-sky-200" : "text-sky-900";
  const linkPaid = theme === "dark" ? "text-emerald-200" : "text-emerald-900";

  return (
    <div className={`flex min-h-screen flex-col ${shell}`}>
      <header className={`border-b ${headerBar}`}>
        <div className="mx-auto flex w-full max-w-5xl flex-nowrap items-center gap-2 px-2 py-1.5 sm:gap-2 sm:px-3 sm:py-2">
          <div className="flex min-w-0 shrink-0 items-center gap-1.5 sm:gap-2">
            <Link
              to={isAdminRoute && adminTok ? "/admin" : "/"}
              className={`inline-flex min-w-0 items-center ${brand}`}
            >
              <BrandLogo />
            </Link>
            <ThemeSwitcher />
          </div>
          <nav
            className={`ml-auto flex min-w-0 max-w-[min(100%,72vw)] shrink-0 items-center justify-end gap-0.5 overflow-x-auto whitespace-nowrap scrollbar-thin sm:max-w-none ${navWrap}`}
          >
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
                <NavLink className={navItemCls} to="/admin/desktop-licensing">
                  Desktop licensing
                </NavLink>
                <NavLink className={navItemCls} to="/admin/desktop-payments">
                  Desktop payments
                </NavLink>
                <NavLink className={navItemCls} to="/admin/desktop-licenses">
                  Desktop licenses
                </NavLink>
                <NavLink className={navItemCls} to="/admin/desktop-installers">
                  Desktop installers
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
                <NavLink className={navItemCls} to="/upgrade">
                  Upgrade
                </NavLink>
                <NavLink className={navItemCls} to="/software">
                  Software
                </NavLink>
                <NavLink className={navItemCls} to="/software/licenses">
                  My licenses
                </NavLink>
                <NavLink className={navItemCls} to="/software/downloads">
                  Downloads
                </NavLink>
                <NavLink className={navItemCls} to="/profile">
                  Profile
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
          {!isLandingHome ? <HeaderBackButton /> : null}
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
      {showSubscriptionStrip && subBanner ? (
        <div
          className={subBanner.kind === "paid" ? paidBannerCls : trialBannerCls}
          role="status"
        >
          {subBanner.kind === "trial" ? (
            <>
              <span className="font-medium">FIR company trial</span> · Plan <strong>{subBanner.planType}</strong> ·{" "}
              <strong>{daysLabel(subBanner.daysLeft)}</strong> left
              {subBanner.trialEndsLabel ? (
                <>
                  {" "}
                  (ends <strong>{subBanner.trialEndsLabel}</strong>)
                </>
              ) : null}
              .{" "}
              <Link className={`font-semibold underline ${linkTrial}`} to="/upgrade">
                Upgrade
              </Link>{" "}
              or{" "}
              <Link className={`font-semibold underline ${linkTrial}`} to="/dashboard/billing">
                Usage &amp; billing
              </Link>
              .
            </>
          ) : (
            <>
              <span className="font-medium">Subscription active</span> · Plan <strong>{subBanner.planType}</strong> ·{" "}
              <strong>{daysLabel(subBanner.daysLeft)}</strong> until renewal
              {subBanner.subscriptionEndsLabel ? (
                <>
                  {" "}
                  (ends <strong>{subBanner.subscriptionEndsLabel}</strong>)
                </>
              ) : null}
              .{" "}
              <Link className={`font-semibold underline ${linkPaid}`} to="/dashboard/billing">
                Usage &amp; billing
              </Link>
              {subBanner.daysLeft <= 14 ? (
                <>
                  {" "}
                  ·{" "}
                  <Link className={`font-semibold underline ${linkPaid}`} to="/upgrade">
                    Renew / upgrade
                  </Link>
                </>
              ) : null}
              .
            </>
          )}
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
