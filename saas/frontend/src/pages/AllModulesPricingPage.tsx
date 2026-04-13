import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api";
import { QMS_MODULES } from "../moduleCatalog";

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
  trial_days: number;
  usage_limit: number;
  fir_plan_type: string | null;
};

/**
 * Full catalog: FIR tiers + QMS modules. Same data as the landing page pricing section.
 * Used for "All module pricing" — never redirects logged-in users to FIR-only workspace pricing.
 */
export default function AllModulesPricingPage() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [pricingMods, setPricingMods] = useState<PricingModule[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [p, all] = await Promise.all([
          apiFetch<Plan[]>("/api/subscription/plans"),
          apiFetch<PricingModule[]>("/api/pricing/modules"),
        ]);
        setPlans(p);
        setPricingMods(all);
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Could not load pricing");
      }
    })();
  }, []);

  const qmsPriceRow = (moduleName: string) => pricingMods.find((x) => x.module_name === moduleName);

  return (
    <div className="space-y-12 pb-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-white">All module pricing</h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-400">
          FIR tiers and QMS add-ons. Amounts are loaded from the pricing catalog. Use{" "}
          <Link className="text-brand-500 hover:underline" to="/workspace/pricing">
            FIR pricing
          </Link>{" "}
          inside the FIR workspace for the in-context upgrade flow.
        </p>
      </div>

      {err && <p className="text-sm text-red-400">{err}</p>}

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-2xl border border-brand-500/30 bg-gradient-to-br from-brand-950/50 to-slate-900/80 p-6">
          <h2 className="text-lg font-semibold text-white">FIR Automation</h2>
          <p className="mt-2 text-sm text-slate-400">Usage-based tiers for inspection and reports.</p>
          <div className="mt-6 space-y-4">
            {plans.length === 0 && !err ? (
              <p className="text-sm text-slate-500">Loading…</p>
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
        </div>

        <div className="space-y-4 rounded-2xl border border-slate-800 bg-slate-900/40 p-6">
          <h2 className="text-lg font-semibold text-white">QMS modules</h2>
          <p className="text-sm text-slate-500">Subscribe individually when enabled for your account.</p>
          <ul className="space-y-3">
            {QMS_MODULES.map((m) => {
              const row = qmsPriceRow(m.moduleName);
              return (
                <li key={m.slug}>
                  <Link
                    to={`/pricing/modules/${m.slug}`}
                    className="flex items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-950/40 px-4 py-3 transition hover:border-slate-600"
                  >
                    <span className="font-medium text-slate-200">{m.title}</span>
                    <span className="text-sm font-semibold text-slate-300">
                      {row ? `₹${row.monthly_price.toLocaleString("en-IN")}/mo` : "—"}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </div>
  );
}
