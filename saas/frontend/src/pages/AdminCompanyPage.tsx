import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiFetch } from "../api";

type Company = {
  id: number;
  company_name: string;
  vendor_code: string;
  trial_start_date: string;
  trial_end_date: string;
  subscription_start: string | null;
  subscription_end: string | null;
  plan_type: string;
  subscription_status: string;
};

type Usage = {
  company_id: number;
  monthly_invoice_count: number;
  monthly_fir_reports: number;
  monthly_usage_combined: number;
  trial_start: string;
  trial_end: string;
  subscription_start: string | null;
  subscription_end: string | null;
  plan_type: string;
  subscription_status: string;
};

type FirIntel = {
  as_of: string;
  company_id: number;
  fy_monthly_reports?: {
    fy_start_year: number;
    fy_label: string;
    fy_total: number;
    months: Array<{
      year: number;
      month: number;
      label: string;
      count: number;
    }>;
  };
  summary: {
    total_report_events: number;
    distinct_part_customer_pairs: number;
    repeated_part_pairs: number;
    rhythm_part_pairs: Record<string, number>;
  };
  customers: Array<{
    id: number | null;
    vendor_code: string | null;
    name: string;
    avg_reports_per_day: number;
    total_reports: number;
    distinct_parts: number;
    parts: Array<{
      part_no: string;
      description: string;
      report_count: number;
      median_quantity?: number | null;
      is_repeat: boolean;
      first_report_date: string;
      last_report_date: string;
      median_interval_days: number | null;
      days_since_last_report: number;
      avg_reports_per_day_in_span: number;
      rhythm: string;
    }>;
  }>;
};

function formatExpectedQty(medianQuantity: number | null | undefined): string {
  if (medianQuantity == null || !Number.isFinite(medianQuantity)) return "—";
  if (Number.isInteger(medianQuantity)) return String(medianQuantity);
  const rounded = Math.round(medianQuantity * 10_000) / 10_000;
  return String(rounded).replace(/(\.\d*?[1-9])0+$/, "$1").replace(/\.0+$/, "");
}

function FirFyReportsBarChart({
  fyLabel,
  months,
  fyTotal,
}: {
  fyLabel: string;
  fyTotal: number;
  months: Array<{ label: string; count: number }>;
}) {
  const max = Math.max(1, ...months.map((m) => m.count));
  const subtitle = `April–March · ${fyTotal.toLocaleString()} FIR rows logged this FY (by generation date)`;
  return (
    <div
      className="rounded-lg border border-slate-800 bg-slate-950/50 p-4"
      role="img"
      aria-label={`FIR reports by month for financial year ${fyLabel}. ${subtitle}`}
    >
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
        FIR reports by month — FY {fyLabel}
      </p>
      <p className="mt-1 text-xs text-slate-500">{subtitle}</p>
      <div className="mt-6 flex items-end gap-1 sm:gap-2">
        {months.map((m, i) => (
          <div
            key={`fy-${fyLabel}-${m.year}-${m.month}-${i}`}
            className="flex min-w-0 flex-1 flex-col items-center gap-1"
          >
            <span className="text-[10px] font-semibold tabular-nums text-slate-200 sm:text-xs">{m.count}</span>
            <div className="flex h-36 w-full items-end justify-center">
              <div
                className="w-[85%] max-w-10 rounded-t bg-blue-600/90 transition-[height] duration-150"
                style={{
                  height: `${m.count === 0 ? 0 : Math.max(8, (m.count / max) * 100)}%`,
                }}
                title={`${m.label}: ${m.count}`}
              />
            </div>
            <span className="w-full truncate text-center text-[9px] text-slate-500 sm:text-[10px]">{m.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function AdminCompanyPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const [company, setCompany] = useState<Company | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [users, setUsers] = useState<{ id: number; email: string; name: string | null }[]>([]);
  const [plan, setPlan] = useState("basic");
  const [extendDays, setExtendDays] = useState(30);
  const [msg, setMsg] = useState<string | null>(null);
  const [intel, setIntel] = useState<FirIntel | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteErr, setDeleteErr] = useState<string | null>(null);

  async function load() {
    if (!id) return;
    const cid = Number(id);
    const [c, u, usr, fi] = await Promise.all([
      apiFetch<Company>(`/admin/companies/${cid}`, { token: "admin" }),
      apiFetch<Usage>(`/admin/companies/${cid}/usage`, { token: "admin" }),
      apiFetch<{ id: number; email: string; name: string | null }[]>(`/admin/companies/${cid}/users`, {
        token: "admin",
      }),
      apiFetch<FirIntel>(`/admin/companies/${cid}/fir-intelligence`, { token: "admin" }),
    ]);
    setCompany(c);
    setUsage(u);
    setUsers(usr);
    setIntel(fi);
    setPlan(c.plan_type);
  }

  useEffect(() => {
    const t = localStorage.getItem("fir_admin_token");
    if (!t) {
      nav("/login");
      return;
    }
    load().catch(() => nav("/login"));
  }, [id, nav]);

  async function patch(body: object) {
    if (!id) return;
    setMsg(null);
    const c = await apiFetch<Company>(`/admin/companies/${id}`, {
      method: "PATCH",
      token: "admin",
      body: JSON.stringify(body),
    });
    setCompany(c);
    await load();
    setMsg("Updated.");
  }

  async function deleteTenantPermanently() {
    if (!id || !company) return;
    const cid = Number(id);
    const proceed = window.confirm(
      `Permanently delete tenant "${company.company_name}" and ALL data (users, FIR customers, parts, invoices, FIR intelligence, uploads log, settings)? This cannot be undone.`,
    );
    if (!proceed) return;
    const typed = window.prompt(`Type the vendor code ${company.vendor_code} to confirm:`);
    if (typed == null) return;
    if (typed.trim() !== company.vendor_code) {
      setDeleteErr("Vendor code did not match. Nothing was deleted.");
      return;
    }
    setDeleteBusy(true);
    setDeleteErr(null);
    try {
      await apiFetch(`/admin/companies/${cid}`, { method: "DELETE", token: "admin" });
      nav("/admin");
    } catch (e) {
      setDeleteErr(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setDeleteBusy(false);
    }
  }

  async function activate(e: FormEvent) {
    e.preventDefault();
    await patch({ action: "activate", plan_type: plan });
  }

  if (!company || !usage) {
    return <p className="text-slate-400">Loading…</p>;
  }

  return (
    <div className="space-y-8">
      <Link className="text-sm text-brand-600 hover:underline" to="/admin">
        ← Back to admin
      </Link>
      <div>
        <h1 className="text-2xl font-semibold text-white">{company.company_name}</h1>
        <p className="text-sm text-slate-400">
          Vendor <span className="font-mono text-slate-200">{company.vendor_code}</span>
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4 text-sm text-slate-300">
          <p>Trial: {usage.trial_start} → {usage.trial_end}</p>
          <p className="mt-2">
            Subscription: {usage.subscription_start || "—"} → {usage.subscription_end || "—"}
          </p>
          <p className="mt-2">
            Status: <span className="text-white">{usage.subscription_status}</span> · Plan:{" "}
            <span className="text-white">{usage.plan_type}</span>
          </p>
          <p className="mt-2">
            Monthly v2 invoices: {usage.monthly_invoice_count} · FIR report rows: {usage.monthly_fir_reports} · Combined:{" "}
            {usage.monthly_usage_combined}
          </p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
          <p className="text-xs uppercase text-slate-500">Users</p>
          <ul className="mt-2 space-y-1 text-sm text-slate-300">
            {users.length === 0 ? (
              <li className="text-slate-500">No workspace logins for this tenant.</li>
            ) : (
              users.map((u) => (
                <li key={u.id}>
                  {u.email} {u.name ? `(${u.name})` : ""}
                </li>
              ))
            )}
          </ul>
          <p className="mt-3 text-xs text-slate-500">
            <Link className="text-brand-600 hover:underline" to="/admin/users">
              Browse all tenant users &amp; FIR customers
            </Link>
          </p>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 space-y-6">
        <h2 className="text-lg font-semibold text-white">Actions</h2>
        <form className="flex flex-wrap items-end gap-3" onSubmit={activate}>
          <div>
            <label className="block text-xs text-slate-500">Plan on activate</label>
            <select
              className="mt-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
              value={plan}
              onChange={(e) => setPlan(e.target.value)}
            >
              <option value="basic">basic</option>
              <option value="pro">pro</option>
              <option value="enterprise">enterprise</option>
            </select>
          </div>
          <button
            type="submit"
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-500"
          >
            Activate subscription
          </button>
        </form>

        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs text-slate-500">Extend (days)</label>
            <input
              type="number"
              className="mt-1 w-32 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
              value={extendDays}
              onChange={(e) => setExtendDays(Number(e.target.value))}
            />
          </div>
          <button
            type="button"
            className="rounded-lg border border-slate-600 px-4 py-2 text-sm text-slate-100 hover:bg-slate-800"
            onClick={() => patch({ action: "extend", extend_days: extendDays })}
          >
            Extend subscription
          </button>
        </div>

        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            className="rounded-lg border border-slate-600 px-4 py-2 text-sm text-slate-100 hover:bg-slate-800"
            onClick={() => patch({ action: "set_plan", plan_type: plan })}
          >
            Set plan only
          </button>
          <button
            type="button"
            className="rounded-lg border border-red-900/60 px-4 py-2 text-sm text-red-300 hover:bg-red-950/40"
            onClick={() => patch({ action: "mark_expired" })}
          >
            Mark expired
          </button>
        </div>
        {msg && <p className="text-sm text-emerald-400">{msg}</p>}
      </div>

      <div className="rounded-2xl border border-red-900/50 bg-red-950/15 p-6 space-y-3">
        <h2 className="text-lg font-semibold text-red-200">Delete tenant</h2>
        <p className="text-sm text-slate-400">
          Removes this company from the admin list and deletes all related workspace data. Use this after offboarding a
          customer. To remove only sign-in accounts, use{" "}
          <Link className="text-brand-500 hover:underline" to="/admin/users">
            Users &amp; customers
          </Link>{" "}
          instead.
        </p>
        {deleteErr && <p className="text-sm text-red-400">{deleteErr}</p>}
        <button
          type="button"
          disabled={deleteBusy}
          className="rounded-lg border border-red-700 bg-red-950/40 px-4 py-2 text-sm font-semibold text-red-100 hover:bg-red-900/50 disabled:opacity-50"
          onClick={() => void deleteTenantPermanently()}
        >
          {deleteBusy ? "Deleting…" : "Delete tenant permanently"}
        </button>
      </div>

      {intel && (
        <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 space-y-6">
          <div>
            <h2 className="text-lg font-semibold text-white">FIR intelligence (admin)</h2>
            <p className="mt-1 text-xs text-slate-500">
              Cadence from logged FIR batches: <strong className="text-slate-400">running</strong> ≈ every 1–3 days,{" "}
              <strong className="text-slate-400">regular</strong> 3–10 days, <strong className="text-slate-400">occasional</strong>{" "}
              11–30 days, <strong className="text-slate-400">stranger</strong> sparse or quiet &gt;30 days,{" "}
              <strong className="text-slate-400">new</strong> first/only touch in the last 30 days. Data as of {intel.as_of}.
            </p>
          </div>

          {intel.fy_monthly_reports && (
            <FirFyReportsBarChart
              fyLabel={intel.fy_monthly_reports.fy_label}
              months={intel.fy_monthly_reports.months}
              fyTotal={intel.fy_monthly_reports.fy_total}
            />
          )}

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 text-sm">
            <IntelStat label="FIR events (all time)" value={intel.summary.total_report_events} />
            <IntelStat label="Part × customer pairs" value={intel.summary.distinct_part_customer_pairs} />
            <IntelStat label="Repeating pairs (2+)" value={intel.summary.repeated_part_pairs} />
            <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
              <p className="text-xs uppercase text-slate-500">By rhythm (pairs)</p>
              <p className="mt-1 text-slate-300">
                {Object.entries(intel.summary.rhythm_part_pairs)
                  .map(([k, v]) => `${k}: ${v}`)
                  .join(" · ") || "—"}
              </p>
            </div>
          </div>

          <div className="space-y-8">
            {intel.customers.map((cust) => (
              <div key={`${cust.id ?? "u"}-${cust.name}`} className="rounded-xl border border-slate-800 bg-slate-950/30 p-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h3 className="text-base font-semibold text-white">{cust.name}</h3>
                  <p className="text-xs text-slate-500">
                    {cust.vendor_code ? <span className="font-mono text-slate-400">{cust.vendor_code}</span> : null}
                    {cust.vendor_code ? " · " : null}
                    avg {cust.avg_reports_per_day}/day · {cust.total_reports} FIR rows · {cust.distinct_parts} parts
                  </p>
                </div>
                {cust.parts.length === 0 ? (
                  <p className="mt-2 text-sm text-slate-500">No logged FIR reports for this customer yet.</p>
                ) : (
                  <div className="mt-3 overflow-x-auto">
                    <table className="min-w-full text-left text-xs text-slate-300">
                      <thead className="border-b border-slate-800 text-slate-500">
                        <tr>
                          <th className="py-2 pr-3">Part</th>
                          <th className="py-2 pr-3">Description</th>
                          <th className="py-2 pr-2">Reports</th>
                          <th className="py-2 pr-2">Expected QTY</th>
                          <th className="py-2 pr-2">Repeat</th>
                          <th className="py-2 pr-2">Median gap (d)</th>
                          <th className="py-2 pr-2">Since last</th>
                          <th className="py-2 pr-2">Rhythm</th>
                          <th className="py-2">Span avg/d</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/80">
                        {cust.parts.map((p) => (
                          <tr key={`${cust.id ?? "u"}-${p.part_no}`}>
                            <td className="py-2 pr-3 font-mono text-slate-200">{p.part_no}</td>
                            <td className="max-w-[200px] truncate py-2 pr-3 text-slate-400" title={p.description}>
                              {p.description || "—"}
                            </td>
                            <td className="py-2 pr-2">{p.report_count}</td>
                            <td className="py-2 pr-2 tabular-nums" title="Median quantity across logged FIR rows for this part">
                              {formatExpectedQty(p.median_quantity)}
                            </td>
                            <td className="py-2 pr-2">{p.is_repeat ? "yes" : "no"}</td>
                            <td className="py-2 pr-2">{p.median_interval_days ?? "—"}</td>
                            <td className="py-2 pr-2">{p.days_since_last_report}d</td>
                            <td className="py-2 pr-2 capitalize text-amber-200/90">{p.rhythm}</td>
                            <td className="py-2">{p.avg_reports_per_day_in_span}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function IntelStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
      <p className="text-xs uppercase text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-semibold text-white">{value}</p>
    </div>
  );
}
