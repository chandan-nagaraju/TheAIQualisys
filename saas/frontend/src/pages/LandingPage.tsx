import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api";
import { QMS_MODULES } from "../moduleCatalog";
import BrandLogo from "../components/BrandLogo";
import { useTheme } from "../theme/ThemeContext";

type Plan = {
  plan_type: string;
  name: string;
  price_inr: number;
  min_invoices: number;
  max_invoices: number | null;
  highlight?: string | null;
};

type PricingModule = {
  module_name: string;
  display_name: string;
  monthly_price: number;
  yearly_price: number | null;
  fir_plan_type: string | null;
};

export default function LandingPage() {
  const { theme } = useTheme();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [pricingMods, setPricingMods] = useState<PricingModule[]>([]);
  const [planErr, setPlanErr] = useState<string | null>(null);
  const signedIn = typeof localStorage !== "undefined" && !!localStorage.getItem("fir_token");

  const heroTitleClass =
    theme === "dark" ? "mt-6 text-4xl font-bold tracking-tight text-white sm:text-5xl" : "mt-6 text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl";
  const heroDescClass =
    theme === "dark" ? "mx-auto mt-6 max-w-2xl text-lg text-slate-400" : "mx-auto mt-6 max-w-2xl text-lg text-slate-600";
  const primaryBtnClass =
    "inline-flex rounded-xl bg-brand-600 px-8 py-3 text-sm font-semibold text-white shadow-lg shadow-brand-900/30 hover:bg-brand-500";
  const secondaryBtnClass =
    theme === "dark"
      ? "inline-flex rounded-xl border border-slate-600 bg-slate-900/40 px-8 py-3 text-sm font-semibold text-white hover:border-slate-500"
      : "inline-flex rounded-xl border border-slate-300 bg-white px-8 py-3 text-sm font-semibold text-slate-900 hover:bg-slate-100";
  const sectionTitleClass = theme === "dark" ? "text-center text-2xl font-semibold text-white" : "text-center text-2xl font-semibold text-slate-900";
  const sectionDescClass = theme === "dark" ? "mx-auto mt-2 max-w-xl text-center text-sm text-slate-400" : "mx-auto mt-2 max-w-xl text-center text-sm text-slate-600";

  useEffect(() => {
    (async () => {
      try {
        const [p, all] = await Promise.all([
          apiFetch<Plan[]>("/subscription/plans"),
          apiFetch<PricingModule[]>("/api/pricing/modules"),
        ]);
        setPlans(p);
        setPricingMods(all);
      } catch (e) {
        setPlanErr(e instanceof Error ? e.message : "Could not load pricing");
      }
    })();
  }, []);

  const qmsPrice = (moduleName: string) =>
    pricingMods.find((x) => x.module_name === moduleName)?.monthly_price;

  return (
    <div className="space-y-20 pb-16">
      <section className="text-center">
        <div className="flex justify-center">
          <BrandLogo
            size="lg"
            className={theme === "dark" ? "text-white" : theme === "grey" ? "text-zinc-900" : "text-slate-900"}
          />
        </div>
        <h1 className={heroTitleClass}>
          AI-Powered Quality Management System
        </h1>
        <p className={heroDescClass}>
          Automate FIR, RC2A, PPAP &amp; IATF documentation — modular subscriptions so you only pay for what you use.
        </p>
        <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
          {signedIn ? (
            <>
              <Link
                to="/dashboard"
                className={primaryBtnClass}
              >
                Module dashboard
              </Link>
              <Link
                to="/workspace/dashboard"
                className={secondaryBtnClass}
              >
                Open FIR workspace
              </Link>
            </>
          ) : (
            <>
              <Link
                to="/signup"
                className={primaryBtnClass}
              >
                Get Started
              </Link>
              <Link
                to="/login"
                className={secondaryBtnClass}
              >
                Login
              </Link>
            </>
          )}
        </div>
      </section>

      <section>
        <h2 className={sectionTitleClass}>Product status</h2>
        <p className={sectionDescClass}>
          Ship quality workflows incrementally. FIR is production-ready; additional modules are rolling out.
        </p>
        <ul className="mx-auto mt-10 max-w-2xl divide-y divide-slate-800 rounded-2xl border border-slate-800 bg-slate-900/40">
          <li className="flex items-center justify-between gap-4 px-6 py-4">
            <span className="font-medium text-slate-200">FIR Automation</span>
            <span className="rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-semibold text-emerald-400">
              Available now
            </span>
          </li>
          {QMS_MODULES.map((m) => (
            <li key={m.slug} className="flex items-center justify-between gap-4 px-6 py-4">
              <span className="font-medium text-slate-200">{m.title}</span>
              <span className="rounded-full bg-amber-500/15 px-3 py-1 text-xs font-semibold text-amber-300">
                Under development
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className={sectionTitleClass}>Module pricing</h2>
        <p className={sectionDescClass}>
          Modules can be subscribed individually. All amounts below are loaded from our pricing catalog.
        </p>

        {planErr && <p className="mt-6 text-center text-sm text-red-400">{planErr}</p>}

        <div className="mt-10 grid gap-6 lg:grid-cols-2">
          <div className="rounded-2xl border border-brand-500/30 bg-gradient-to-br from-brand-950/50 to-slate-900/80 p-6">
            <h3 className="text-lg font-semibold text-white">FIR Automation</h3>
            <p className="mt-2 text-sm text-slate-400">Final Inspection Reports — usage-based tiers.</p>
            <div className="mt-6 space-y-4">
              {plans.length === 0 && !planErr ? (
                <p className="text-sm text-slate-500">Loading plans…</p>
              ) : (
                plans.map((plan) => (
                  <div key={plan.plan_type} className="rounded-xl border border-slate-700/80 bg-slate-950/50 px-4 py-3">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="font-medium text-slate-200">{plan.name}</span>
                      <span className="text-lg font-bold text-white">
                        ₹{plan.price_inr.toLocaleString("en-IN")}
                        <span className="text-sm font-normal text-slate-500">/month</span>
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-slate-500">
                      {plan.max_invoices == null
                        ? `${plan.min_invoices}+ invoices / month`
                        : `${plan.min_invoices}–${plan.max_invoices} invoices / month`}
                    </p>
                  </div>
                ))
              )}
            </div>
            <Link
              to="/signup"
              className="mt-6 inline-flex w-full justify-center rounded-lg bg-brand-600 py-2.5 text-sm font-semibold text-white hover:bg-brand-500"
            >
              Start with FIR
            </Link>
          </div>

          <div className="space-y-4 rounded-2xl border border-slate-800 bg-slate-900/40 p-6">
            <h3 className="text-lg font-semibold text-white">More modules</h3>
            <p className="text-sm text-slate-500">Subscribe when each module is enabled for your account.</p>
            <ul className="space-y-3">
              {QMS_MODULES.map((m) => {
                const p = qmsPrice(m.moduleName);
                return (
                  <li
                    key={m.slug}
                    className="flex items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-950/40 px-4 py-3"
                  >
                    <span className="text-slate-300">{m.title}</span>
                    <span className="text-sm font-semibold text-slate-400">
                      {p != null ? `₹${p.toLocaleString("en-IN")}/mo` : "—"}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      </section>
    </div>
  );
}
