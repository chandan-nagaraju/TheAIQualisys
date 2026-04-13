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

  async function load() {
    if (!id) return;
    const cid = Number(id);
    const [c, u, usr, fi] = await Promise.all([
      apiFetch<Company>(`/api/admin/companies/${cid}`, { token: "admin" }),
      apiFetch<Usage>(`/api/admin/companies/${cid}/usage`, { token: "admin" }),
      apiFetch<{ id: number; email: string; name: string | null }[]>(`/api/admin/companies/${cid}/users`, {
        token: "admin",
      }),
      apiFetch<FirIntel>(`/api/admin/companies/${cid}/fir-intelligence`, { token: "admin" }),
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
    const c = await apiFetch<Company>(`/api/admin/companies/${id}`, {
      method: "PATCH",
      token: "admin",
      body: JSON.stringify(body),
    });
    setCompany(c);
    await load();
    setMsg("Updated.");
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
            {users.map((u) => (
              <li key={u.id}>
                {u.email} {u.name ? `(${u.name})` : ""}
              </li>
            ))}
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
