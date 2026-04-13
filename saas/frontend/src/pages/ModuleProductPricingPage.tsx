import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { apiFetch } from "../api";
import { getModuleBySlug } from "../moduleCatalog";

type UpgradeInfo = { upi_id: string; whatsapp_url: string; message: string };

type PricingRow = {
  module_name: string;
  monthly_price: number;
  yearly_price: number | null;
  trial_days: number;
};

export default function ModuleProductPricingPage() {
  const { slug } = useParams<{ slug: string }>();
  const loc = useLocation();
  const def = slug ? getModuleBySlug(slug) : undefined;
  const trialState = loc.state as { trialEnded?: boolean; message?: string } | null;
  const [info, setInfo] = useState<UpgradeInfo | null>(null);
  const [priceRow, setPriceRow] = useState<PricingRow | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [u, all] = await Promise.all([
          apiFetch<UpgradeInfo>("/api/subscription/upgrade-info"),
          apiFetch<PricingRow[]>("/api/pricing/modules"),
        ]);
        setInfo(u);
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

  const enrollUrl =
    info &&
    (() => {
      try {
        const u = new URL(info.whatsapp_url);
        const enrollText = `[TheAIQualisys — ${def.title}] I would like to enroll in this module. ${info.message}`;
        u.searchParams.set("text", enrollText);
        return u.toString();
      } catch {
        return info.whatsapp_url;
      }
    })();

  return (
    <div className="mx-auto max-w-lg space-y-8">
      <div>
        <Link to="/pricing/all-modules" className="text-sm font-medium text-brand-500 hover:underline">
          ← All module pricing
        </Link>
        <h1 className="mt-4 text-3xl font-bold text-white">{def.title}</h1>
        <p className="mt-2 text-slate-400">{def.shortDescription}</p>
      </div>

      {(trialState?.trialEnded || trialState?.message) && (
        <div className="rounded-xl border border-amber-600/40 bg-amber-950/30 px-4 py-3 text-sm text-amber-100">
          {trialState?.message ||
            "Your trial has ended. Please enroll to continue using this module."}
        </div>
      )}

      <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6">
        <p className="text-xs uppercase tracking-wide text-slate-500">Monthly</p>
        <p className="mt-2 text-4xl font-bold text-white">
          {priceRow ? (
            <>
              ₹{priceRow.monthly_price.toLocaleString("en-IN")}
              <span className="text-lg font-normal text-slate-500">/month</span>
            </>
          ) : (
            <span className="text-slate-500">—</span>
          )}
        </p>
        {priceRow?.yearly_price != null && (
          <p className="mt-1 text-sm text-slate-400">
            Yearly: ₹{priceRow.yearly_price.toLocaleString("en-IN")}
          </p>
        )}
        <p className="mt-2 text-xs text-slate-500">Trial: {priceRow?.trial_days ?? "—"} days (when you open the module)</p>
        <ul className="mt-6 space-y-2 text-sm text-slate-300">
          {def.features.map((f) => (
            <li key={f} className="flex gap-2">
              <span className="text-brand-500">✓</span>
              {f}
            </li>
          ))}
        </ul>
      </div>

      {err && <p className="text-sm text-red-400">{err}</p>}

      {enrollUrl && (
        <a
          href={enrollUrl}
          target="_blank"
          rel="noreferrer"
          className="flex w-full justify-center rounded-xl bg-emerald-600 py-3 text-sm font-semibold text-white hover:bg-emerald-500"
        >
          Enroll Now
        </a>
      )}

      <p className="text-center text-xs text-slate-500">
        Modules can be subscribed individually. Our team will confirm payment and activate your account.
      </p>

      <p className="text-center text-sm text-slate-400">
        Already a customer?{" "}
        <Link className="text-brand-500 hover:underline" to="/login">
          Login
        </Link>
      </p>
    </div>
  );
}
