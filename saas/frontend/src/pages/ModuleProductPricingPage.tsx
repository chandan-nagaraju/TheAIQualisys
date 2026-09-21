import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { apiFetch } from "../api";
import { getModuleBySlug } from "../moduleCatalog";
import { buildUpgradeSearch } from "./upgradeHelpers";

type PricingRow = {
  module_name: string;
  display_name?: string;
  monthly_price: number;
  yearly_price: number | null;
  trial_days: number;
  listing_active?: boolean;
};

/**
 * Per-module pricing, matching FIR: plan card → Buy → billing period → UPI QR pay page.
 */
export default function ModuleProductPricingPage() {
  const { slug } = useParams<{ slug: string }>();
  const loc = useLocation();
  const def = slug ? getModuleBySlug(slug) : undefined;
  const trialState = loc.state as { trialEnded?: boolean; message?: string } | null;
  const [priceRow, setPriceRow] = useState<PricingRow | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const loggedIn = typeof localStorage !== "undefined" && !!localStorage.getItem("fir_token");

  useEffect(() => {
    (async () => {
      try {
        const all = await apiFetch<PricingRow[]>("/api/pricing/modules");
        const d = slug ? getModuleBySlug(slug) : undefined;
        setPriceRow(d ? all.find((r) => r.module_name === d.moduleName) ?? null : null);
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Failed to load");
      }
    })();
  }, [slug]);

  if (!def || !slug) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-8 text-center text-slate-400">
        Module not found.{" "}
        <Link className="text-brand-500 hover:underline" to="/">
          Home
        </Link>
      </div>
    );
  }

  const buyHref =
    priceRow &&
    `/upgrade?${buildUpgradeSearch({
      moduleKey: def.moduleName,
      planName: def.title,
      planType: def.moduleName,
      priceInr: priceRow.monthly_price,
    })}`;

  return (
    <div className="space-y-10 pb-6">
      <div className="mx-auto max-w-3xl text-center">
        <Link to="/pricing/all-modules" className="text-sm font-medium text-brand-500 hover:underline">
          ← All module pricing
        </Link>
        <h1 className="mt-4 text-3xl font-bold tracking-tight text-white sm:text-4xl">{def.title} pricing</h1>
        <p className="mx-auto mt-5 max-w-3xl text-base leading-relaxed text-slate-400">
          {def.shortDescription} Start with a{" "}
          <span className="font-semibold text-brand-600">{priceRow?.trial_days ?? "—"}-day free trial</span> when you
          open the module. To subscribe, choose this plan, pick a billing period, then pay with{" "}
          <strong className="text-slate-300">UPI QR</strong> on the payment page.
        </p>
      </div>

      {(trialState?.trialEnded || trialState?.message) && (
        <div className="mx-auto max-w-3xl rounded-xl border border-amber-600/40 bg-amber-950/30 px-4 py-3 text-sm text-amber-100">
          {trialState?.message || "Your trial has ended. Please subscribe via UPI to continue using this module."}
        </div>
      )}

      {err && <p className="text-center text-sm text-red-400">{err}</p>}

      <div className="mx-auto mt-6 grid max-w-lg gap-8">
        <div className="relative flex h-full flex-col rounded-2xl border border-slate-800 bg-slate-900/50 p-7 sm:p-8">
          <h2 className="text-lg font-semibold text-white">{def.title}</h2>
          <p className="mt-4 text-3xl font-bold text-white sm:text-4xl">
            {priceRow ? (
              <>
                ₹{priceRow.monthly_price.toLocaleString("en-IN")}
                <span className="text-base font-normal text-slate-400">/month</span>
              </>
            ) : (
              <span className="text-slate-500">—</span>
            )}
          </p>
          {priceRow?.yearly_price != null && (
            <p className="mt-2 text-sm text-slate-400">
              Yearly catalog price: ₹{priceRow.yearly_price.toLocaleString("en-IN")}
            </p>
          )}
          <ul className="mt-6 space-y-2 text-sm text-slate-300">
            {def.features.map((f) => (
              <li key={f} className="flex gap-2">
                <span className="text-brand-500">✓</span>
                {f}
              </li>
            ))}
          </ul>
          {buyHref ? (
            <Link
              to={buyHref}
              className="mt-8 inline-flex min-h-11 items-center justify-center rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-brand-700"
            >
              Buy — pay with UPI QR
            </Link>
          ) : (
            <p className="mt-8 text-sm text-slate-500">Pricing is not available yet.</p>
          )}
        </div>
      </div>

      <div className="mx-auto mt-8 max-w-4xl rounded-2xl border border-slate-800 bg-slate-900/40 p-7 text-center sm:p-8">
        <h3 className="text-xl font-semibold text-white">Pay via UPI QR</h3>
        <p className="mt-3 text-sm text-slate-400 sm:text-base">
          After you click Buy, choose Month, Quarterly, Half yearly, or Yearly. The next screen shows the UPI QR, UPI
          ID, and Open in UPI app. Then tap Payment Done and send the screenshot on WhatsApp for admin verification.
        </p>
        {!loggedIn && (
          <p className="mt-4 text-sm text-slate-400">
            Already a customer?{" "}
            <Link className="text-brand-500 hover:underline" to="/login">
              Login
            </Link>{" "}
            before Payment Done so we can attach the payment to your company.
          </p>
        )}
      </div>
    </div>
  );
}
