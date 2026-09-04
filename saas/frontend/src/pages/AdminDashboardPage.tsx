import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiFetch } from "../api";
import { AdminSubscriptionReminderButton } from "../components/AdminSubscriptionReminderButton";

type Dash = {
  total_companies: number;
  trial_count: number;
  active_count: number;
  expired_count: number;
  total_invoices: number;
};

type Row = {
  id: number;
  company_name: string;
  vendor_code: string;
  plan_type: string;
  subscription_status: string;
  monthly_usage: number;
  monthly_fir_reports: number;
  monthly_usage_combined: number;
  tenant_user_count: number;
};

export default function AdminDashboardPage() {
  const nav = useNavigate();
  const [dash, setDash] = useState<Dash | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [openCompanyId, setOpenCompanyId] = useState<number | null>(null);
  const [openBusy, setOpenBusy] = useState(false);
  const [openErr, setOpenErr] = useState<string | null>(null);
  useEffect(() => {
    const t = localStorage.getItem("fir_admin_token");
    if (!t) {
      nav("/login");
      return;
    }
    (async () => {
      try {
        const [d, c] = await Promise.all([
          apiFetch<Dash>("/admin/dashboard", { token: "admin" }),
          apiFetch<Row[]>("/admin/companies", { token: "admin" }),
        ]);
        setDash(d);
        setRows(c);
      } catch {
        localStorage.removeItem("fir_admin_token");
        nav("/login");
      }
    })();
  }, [nav]);

  async function openTenantWorkspace(companyId: number) {
    const adminTok = localStorage.getItem("fir_admin_token");
    if (!adminTok) return;
    const row = rows.find((r) => r.id === companyId);
    if (!row || row.tenant_user_count < 1) {
      setOpenErr("That company has no workspace logins. Deleted users do not remove the company — add a user from signup/support or clean up the tenant from Manage.");
      return;
    }
    setOpenBusy(true);
    setOpenErr(null);
    try {
      sessionStorage.setItem("fir_admin_token_backup", adminTok);
      sessionStorage.setItem("fir_impersonating", "1");
      const res = await apiFetch<{ access_token: string }>(`/admin/companies/${companyId}/impersonate`, {
        method: "POST",
        body: "{}",
        token: "admin",
      });
      localStorage.setItem("fir_token", res.access_token);
      localStorage.removeItem("fir_admin_token");
      nav("/dashboard");
    } catch (e) {
      sessionStorage.removeItem("fir_admin_token_backup");
      sessionStorage.removeItem("fir_impersonating");
      setOpenErr(e instanceof Error ? e.message : "Could not open workspace.");
    } finally {
      setOpenBusy(false);
    }
  }

  if (!dash) {
    return <p className="text-slate-400">Loading admin…</p>;
  }

  return (
    <div className="space-y-10">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-semibold text-white">Admin panel</h1>
        <div className="flex flex-wrap gap-2">
          <Link
            to="/admin/users"
            className="inline-flex w-fit rounded-lg border border-amber-700/50 bg-amber-950/30 px-4 py-2 text-sm font-medium text-amber-100 hover:bg-amber-950/50"
          >
            Users &amp; customers (all tenants)
          </Link>
          <Link
            to="/admin/pricing"
            className="inline-flex w-fit rounded-lg border border-slate-600 bg-slate-900/50 px-4 py-2 text-sm font-medium text-slate-200 hover:bg-slate-800"
          >
            Pricing management
          </Link>
          <Link
            to="/admin/desktop-licensing"
            className="inline-flex w-fit rounded-lg border border-slate-600 bg-slate-900/50 px-4 py-2 text-sm font-medium text-slate-200 hover:bg-slate-800"
          >
            Desktop licensing
          </Link>
          <Link
            to="/admin/desktop-payments"
            className="inline-flex w-fit rounded-lg border border-slate-600 bg-slate-900/50 px-4 py-2 text-sm font-medium text-slate-200 hover:bg-slate-800"
          >
            Desktop payments
          </Link>
          <Link
            to="/admin/desktop-licenses"
            className="inline-flex w-fit rounded-lg border border-slate-600 bg-slate-900/50 px-4 py-2 text-sm font-medium text-slate-200 hover:bg-slate-800"
          >
            Desktop licenses
          </Link>
          <Link
            to="/admin/desktop-installers"
            className="inline-flex w-fit rounded-lg border border-slate-600 bg-slate-900/50 px-4 py-2 text-sm font-medium text-slate-200 hover:bg-slate-800"
          >
            Desktop installers
          </Link>
        </div>
        <button
          type="button"
          className="text-sm text-slate-400 hover:text-white"
          onClick={() => {
            localStorage.removeItem("fir_admin_token");
            nav("/login");
          }}
        >
          Log out
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Companies" value={dash.total_companies} />
        <Stat label="Trial" value={dash.trial_count} />
        <Stat label="Active" value={dash.active_count} />
        <Stat label="Expired" value={dash.expired_count} />
      </div>
      <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
        <p className="text-xs uppercase tracking-wide text-slate-500">Total v2 invoices (all tenants)</p>
        <p className="mt-1 text-2xl font-semibold text-white">{dash.total_invoices}</p>
      </div>

      <div className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-800 bg-slate-900/40 p-4">
        <div>
          <label className="text-xs font-medium text-slate-500">Open tenant FIR workspace</label>
          <select
            className="mt-1 block min-w-[16rem] rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
            value={openCompanyId ?? ""}
            onChange={(e) => {
              setOpenErr(null);
              setOpenCompanyId(e.target.value ? Number(e.target.value) : null);
            }}
          >
            <option value="">Select company…</option>
            {rows.map((r) => (
              <option key={r.id} value={r.id} disabled={r.tenant_user_count < 1}>
                {r.company_name} ({r.vendor_code})
                {r.tenant_user_count < 1 ? " — no logins" : ""}
              </option>
            ))}
          </select>
        </div>
        <button
          type="button"
          disabled={
            openCompanyId == null ||
            openBusy ||
            (rows.find((r) => r.id === openCompanyId)?.tenant_user_count ?? 0) < 1
          }
          className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          onClick={() => openCompanyId != null && void openTenantWorkspace(openCompanyId)}
        >
          {openBusy ? "Opening…" : "Open workspace"}
        </button>
        {openErr && <p className="w-full text-sm text-amber-400">{openErr}</p>}
        <p className="w-full text-xs text-slate-500">
          Uses the first login user for that company. <strong className="text-slate-400">0 logins</strong> means no one
          can sign in until you add a user — removing users does not delete the company row. Your admin session is saved
          — use <strong>Exit to admin</strong> in the workspace banner to return.
        </p>
      </div>

      <div>
        <h2 className="text-lg font-semibold text-white">Companies</h2>
        <div className="mt-4 overflow-x-auto rounded-xl border border-slate-800">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-900/80 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Vendor</th>
                <th className="px-4 py-3">Plan</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Logins</th>
                <th className="px-4 py-3">Usage (mo)</th>
                <th className="px-4 py-3 text-slate-500">Inv / FIR</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {rows.map((r) => (
                <tr key={r.id} className="hover:bg-slate-900/40">
                  <td className="px-4 py-3 text-slate-200">{r.company_name}</td>
                  <td className="px-4 py-3 font-mono text-slate-400">{r.vendor_code}</td>
                  <td className="px-4 py-3 text-slate-300">{r.plan_type}</td>
                  <td className="px-4 py-3 text-slate-300">{r.subscription_status}</td>
                  <td
                    className={`px-4 py-3 font-medium tabular-nums ${r.tenant_user_count < 1 ? "text-amber-400" : "text-slate-200"}`}
                    title="Workspace users (company_users) for this tenant"
                  >
                    {r.tenant_user_count}
                  </td>
                  <td className="px-4 py-3 font-medium text-slate-200">{r.monthly_usage_combined}</td>
                  <td className="px-4 py-3 text-xs text-slate-500">
                    {r.monthly_usage} / {r.monthly_fir_reports}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex flex-wrap items-center justify-end gap-2">
                      <AdminSubscriptionReminderButton companyId={r.id} variant="inline" />
                      <Link className="text-brand-600 hover:underline" to={`/admin/companies/${r.id}`}>
                        Manage
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-white">{value}</p>
    </div>
  );
}
