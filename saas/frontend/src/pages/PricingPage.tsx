import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api";

type Plan = {
  plan_type: string;
  name: string;
  price_inr: number;
  min_invoices: number;
  max_invoices: number | null;
  highlight?: string | null;
};

type UpgradeInfo = { upi_id: string; whatsapp_url: string; message: string };

type PricingRow = { module_name: string; trial_days: number; fir_plan_type: string | null };

type Props = {
  /** `workspace` = light shell inside logged-in FIR workspace (no redirect to marketing). */
  variant?: "marketing" | "workspace";
};

export default function PricingPage({ variant = "marketing" }: Props) {
  const ws = variant === "workspace";
  const [plans, setPlans] = useState<Plan[]>([]);
  const [upgrade, setUpgrade] = useState<UpgradeInfo | null>(null);
  const [firTrialDays, setFirTrialDays] = useState<number>(7);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [p, u, all] = await Promise.all([
          apiFetch<Plan[]>("/subscription/plans"),
          apiFetch<UpgradeInfo>("/subscription/upgrade-info"),
          apiFetch<PricingRow[]>("/api/pricing/modules"),
        ]);
        setPlans(p);
        setUpgrade(u);
        const basic = all.find((r) => r.fir_plan_type === "basic");
        if (basic) setFirTrialDays(basic.trial_days);
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Failed to load pricing");
      }
    })();
  }, []);

  const t = {
    h1: ws ? "text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl lg:text-5xl" : "text-3xl font-bold tracking-tight text-white sm:text-4xl lg:text-5xl",
    lead: ws ? "mx-auto mt-5 max-w-3xl text-base leading-relaxed text-slate-600 sm:text-lg" : "mx-auto mt-5 max-w-3xl text-base leading-relaxed text-slate-400 sm:text-lg",
    leadAccent: ws ? "font-semibold text-brand-600" : "font-semibold text-brand-600",
    err: ws ? "mt-8 text-center text-sm text-red-600" : "mt-8 text-center text-sm text-red-400",
    cardBase: ws
      ? "relative flex h-full flex-col rounded-2xl border p-7 sm:p-8"
      : "relative flex h-full flex-col rounded-2xl border p-7 sm:p-8",
    cardEnt: ws
      ? "border-amber-200 bg-gradient-to-b from-amber-50 to-white shadow-md shadow-amber-100/50"
      : "border-amber-500/50 bg-gradient-to-b from-amber-500/10 to-slate-900/40 shadow-lg shadow-amber-500/10",
    cardStd: ws ? "border-slate-200 bg-white shadow-sm transition-shadow hover:shadow-md" : "border-slate-800 bg-slate-900/50",
    badgeEnt: ws ? "inline-flex w-fit rounded-full bg-amber-100 px-3 py-0.5 text-xs font-medium text-amber-900" : "inline-flex w-fit rounded-full bg-amber-500/20 px-3 py-0.5 text-xs font-medium text-amber-200",
    h2: ws ? "text-lg font-semibold text-slate-900" : "text-lg font-semibold text-white",
    price: ws ? "mt-4 text-3xl font-bold text-slate-900 sm:text-4xl" : "mt-4 text-3xl font-bold text-white sm:text-4xl",
    priceSub: ws ? "text-base font-normal text-slate-500" : "text-base font-normal text-slate-400",
    meta: ws ? "mt-4 text-sm text-slate-600" : "mt-4 text-sm text-slate-400",
    highlight: ws ? "mt-4 text-sm text-amber-900/90" : "mt-4 text-sm text-amber-100/90",
    upgradeBox: ws
      ? "mx-auto mt-16 max-w-4xl rounded-2xl border border-slate-200 bg-slate-50 p-7 text-center sm:p-8"
      : "mx-auto mt-16 max-w-4xl rounded-2xl border border-slate-800 bg-slate-900/40 p-7 text-center sm:p-8",
    upgradeH: ws ? "text-xl font-semibold text-slate-900" : "text-xl font-semibold text-white",
    upgradeP: ws ? "mt-3 text-sm text-slate-600 sm:text-base" : "mt-3 text-sm text-slate-400 sm:text-base",
    upgradeFoot: ws ? "mt-4 text-xs text-slate-500 sm:text-sm" : "mt-4 text-xs text-slate-500 sm:text-sm",
  };

  return (
    <div className="space-y-10 pb-6">
      <div className="mx-auto max-w-3xl text-center">
        <h1 className={t.h1}>Simple usage-based pricing</h1>
        <p className={t.lead}>
          Start with a{" "}
          <span className={t.leadAccent}>
            {firTrialDays}-day free trial
          </span>{" "}
          with full access. After the trial you can keep viewing your data; new invoice creation unlocks when your
          subscription is active.
        </p>
      </div>

      {err && <p className={t.err}>{err}</p>}

      <div className="mt-14 grid gap-8 md:grid-cols-2 xl:grid-cols-3">
        {plans.map((plan) => {
          const isEnterprise = plan.plan_type === "enterprise";
          return (
            <div
              key={plan.plan_type}
              className={`${t.cardBase} ${isEnterprise ? t.cardEnt : t.cardStd}`}
            >
              {isEnterprise && (
                <span className={t.badgeEnt}>Best for growing companies</span>
              )}
              <h2 className={t.h2}>{plan.name}</h2>
              <p className={t.price}>
                ₹{plan.price_inr}
                <span className={t.priceSub}>/month</span>
              </p>
              <p className={t.meta}>
                {plan.max_invoices == null
                  ? `${plan.min_invoices}+ invoices / month`
                  : `${plan.min_invoices === 0 ? "0" : plan.min_invoices}–${plan.max_invoices} invoices / month`}
              </p>
              {plan.highlight && <p className={t.highlight}>{plan.highlight}</p>}
              {ws ? (
                <Link
                  to="/dashboard/billing"
                  className="mt-8 inline-flex min-h-11 items-center justify-center rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-brand-700"
                >
                  Usage &amp; billing
                </Link>
              ) : (
                <Link
                  to="/signup"
                  className="mt-8 inline-flex min-h-11 items-center justify-center rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-brand-700"
                >
                  Start trial
                </Link>
              )}
            </div>
          );
        })}
      </div>

      <div className={t.upgradeBox}>
        <h3 className={t.upgradeH}>Upgrade via WhatsApp</h3>
        <p className={t.upgradeP}>
          Pay manually via UPI. Our team activates your subscription after verification.
        </p>
        {upgrade && (
          <a
            href={upgrade.whatsapp_url}
            target="_blank"
            rel="noreferrer"
            className="mt-4 inline-flex items-center justify-center rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-emerald-500"
          >
            Upgrade via WhatsApp
          </a>
        )}
        {upgrade && <p className={t.upgradeFoot}>{upgrade.message}</p>}
      </div>
    </div>
  );
}
