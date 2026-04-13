import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiFetch } from "../api";

export type AdminPricingRow = {
  module_name: string;
  display_name: string;
  monthly_price: number;
  yearly_price: number | null;
  trial_days: number;
  usage_limit: number;
  fir_plan_type: string | null;
  invoice_min: number | null;
  invoice_max: number | null;
  highlight: string | null;
  sort_order: number;
  listing_active: boolean;
};

function RowEditor({ row, onSaved }: { row: AdminPricingRow; onSaved: () => void }) {
  const [display_name, setDisplayName] = useState(row.display_name);
  const [monthly_price, setMonthly] = useState(String(row.monthly_price));
  const [yearly_price, setYearly] = useState(row.yearly_price == null ? "" : String(row.yearly_price));
  const [trial_days, setTrialDays] = useState(String(row.trial_days));
  const [usage_limit, setUsageLimit] = useState(String(row.usage_limit));
  const [invoice_min, setInvMin] = useState(row.invoice_min == null ? "" : String(row.invoice_min));
  const [invoice_max, setInvMax] = useState(row.invoice_max == null ? "" : String(row.invoice_max));
  const [highlight, setHighlight] = useState(row.highlight ?? "");
  const [listingActive, setListingActive] = useState(row.listing_active);
  const [status, setStatus] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setDisplayName(row.display_name);
    setMonthly(String(row.monthly_price));
    setYearly(row.yearly_price == null ? "" : String(row.yearly_price));
    setTrialDays(String(row.trial_days));
    setUsageLimit(String(row.usage_limit));
    setInvMin(row.invoice_min == null ? "" : String(row.invoice_min));
    setInvMax(row.invoice_max == null ? "" : String(row.invoice_max));
    setHighlight(row.highlight ?? "");
    setListingActive(row.listing_active);
    setStatus(null);
    setErr(null);
  }, [row]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setStatus(null);
    const body: Record<string, unknown> = {
      display_name,
      monthly_price: parseInt(monthly_price, 10),
      trial_days: parseInt(trial_days, 10),
      usage_limit: parseInt(usage_limit, 10),
    };
    if (yearly_price.trim() === "") body.yearly_price = null;
    else body.yearly_price = parseInt(yearly_price, 10);
    if (!row.fir_plan_type) {
      body.listing_active = listingActive;
    }
    if (row.fir_plan_type) {
      body.invoice_min = invoice_min.trim() === "" ? null : parseInt(invoice_min, 10);
      body.invoice_max = invoice_max.trim() === "" ? null : parseInt(invoice_max, 10);
      body.highlight = highlight.trim() === "" ? null : highlight;
    }
    try {
      await apiFetch(`/api/admin/pricing-modules/${encodeURIComponent(row.module_name)}`, {
        method: "PATCH",
        body: JSON.stringify(body),
        token: "admin",
      });
      setStatus("Saved.");
      onSaved();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Save failed");
    }
  }

  return (
    <form
      onSubmit={onSubmit}
      className="rounded-xl border border-slate-800 bg-slate-900/50 p-4 space-y-3"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-semibold text-white">{row.display_name}</h3>
        <code className="text-xs text-slate-500">{row.module_name}</code>
      </div>
      {!row.fir_plan_type && (
        <label className="block text-xs text-slate-500">
          Tenant dashboard (QMS card)
          <select
            className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
            value={listingActive ? "active" : "inactive"}
            onChange={(e) => setListingActive(e.target.value === "active")}
          >
            <option value="inactive">Not active — stay tuned only (no trial or pricing on card)</option>
            <option value="active">Active — show trial, pricing teaser, and enroll links</option>
          </select>
        </label>
      )}
      {!row.fir_plan_type && !listingActive && (
        <p className="text-xs text-slate-500">
          Price, trial, and usage below are saved but hidden from users until this module is Active.
        </p>
      )}

      <div className={`grid gap-3 sm:grid-cols-2 lg:grid-cols-4 ${!row.fir_plan_type && !listingActive ? "pointer-events-none opacity-50" : ""}`}>
        <label className="block text-xs text-slate-500">
          Display name
          <input
            className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
            value={display_name}
            onChange={(e) => setDisplayName(e.target.value)}
          />
        </label>
        <label className="block text-xs text-slate-500">
          Monthly (₹)
          <input
            type="number"
            min={0}
            className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
            value={monthly_price}
            onChange={(e) => setMonthly(e.target.value)}
          />
        </label>
        <label className="block text-xs text-slate-500">
          Yearly (₹, optional)
          <input
            type="number"
            min={0}
            className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
            value={yearly_price}
            onChange={(e) => setYearly(e.target.value)}
            placeholder="empty = none"
          />
        </label>
        <label className="block text-xs text-slate-500">
          Trial (days)
          <input
            type="number"
            min={0}
            className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
            value={trial_days}
            onChange={(e) => setTrialDays(e.target.value)}
          />
        </label>
        <label className="block text-xs text-slate-500">
          Usage limit (trial actions for QMS)
          <input
            type="number"
            min={0}
            className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
            value={usage_limit}
            onChange={(e) => setUsageLimit(e.target.value)}
          />
        </label>
        {row.fir_plan_type && (
          <>
            <label className="block text-xs text-slate-500">
              Invoice min (tier)
              <input
                type="number"
                min={0}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
                value={invoice_min}
                onChange={(e) => setInvMin(e.target.value)}
              />
            </label>
            <label className="block text-xs text-slate-500">
              Invoice max cap (empty = unlimited)
              <input
                type="number"
                min={0}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
                value={invoice_max}
                onChange={(e) => setInvMax(e.target.value)}
                placeholder="Enterprise: leave empty"
              />
            </label>
            <label className="block text-xs text-slate-500 sm:col-span-2">
              Highlight (optional)
              <input
                className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
                value={highlight}
                onChange={(e) => setHighlight(e.target.value)}
              />
            </label>
          </>
        )}
      </div>
      {err && <p className="text-xs text-red-400">{err}</p>}
      {status && <p className="text-xs text-emerald-400">{status}</p>}
      <button
        type="submit"
        className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-500"
      >
        Save
      </button>
    </form>
  );
}

export default function AdminPricingPage() {
  const nav = useNavigate();
  const [rows, setRows] = useState<AdminPricingRow[]>([]);
  const [tick, setTick] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadErr, setLoadErr] = useState<string | null>(null);

  useEffect(() => {
    const t = localStorage.getItem("fir_admin_token");
    if (!t) {
      nav("/login");
      return;
    }
    let cancelled = false;
    (async () => {
      setLoading(true);
      setLoadErr(null);
      try {
        const data = await apiFetch<AdminPricingRow[]>("/api/admin/pricing-modules", { token: "admin" });
        if (!cancelled) setRows(data.map((r) => ({ ...r, listing_active: Boolean((r as { listing_active?: boolean }).listing_active) })));
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Failed to load";
        if (!cancelled) {
          if (/not authenticated|invalid token|401/i.test(msg)) {
            localStorage.removeItem("fir_admin_token");
            nav("/login");
            return;
          }
          setLoadErr(msg);
          setRows([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [nav, tick]);

  const firRows = rows.filter((r) => r.fir_plan_type);
  const qmsRows = rows.filter((r) => !r.fir_plan_type);

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-white">Pricing management</h1>
        <Link to="/admin" className="text-sm text-brand-500 hover:underline">
          ← Admin home
        </Link>
      </div>
      <p className="text-sm text-slate-400">
        For each <strong className="text-slate-300">QMS module</strong>, choose <strong>Active</strong> so tenants see trial
        and pricing on the dashboard, or <strong>Not active</strong> for a stay-tuned-only card. FIR plan tiers below are
        unchanged.
      </p>
      <p className="text-sm text-slate-400">
        Saving QMS trial days or usage limits updates existing trial rows for that module.
      </p>

      {loading && <p className="text-sm text-slate-500">Loading pricing catalog…</p>}
      {loadErr && <p className="text-sm text-red-400">{loadErr}</p>}
      {!loading && !loadErr && rows.length === 0 && (
        <p className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-4 py-3 text-sm text-amber-100">
          No pricing rows returned. Restart the API once so defaults are seeded into <code className="text-amber-50">module_pricing</code>, or run{" "}
          <code className="text-amber-50">python scripts/apply_schema_extensions.py</code> from <code className="text-amber-50">saas/backend</code>.
        </p>
      )}

      <section className="space-y-4">
        <h2 className="text-lg font-semibold text-white">FIR Automation (plan tiers)</h2>
        <div className="space-y-4">
          {firRows.map((r) => (
            <RowEditor key={r.module_name} row={r} onSaved={() => setTick((x) => x + 1)} />
          ))}
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-semibold text-white">QMS modules</h2>
        <div className="space-y-4">
          {qmsRows.map((r) => (
            <RowEditor key={r.module_name} row={r} onSaved={() => setTick((x) => x + 1)} />
          ))}
        </div>
      </section>
    </div>
  );
}
