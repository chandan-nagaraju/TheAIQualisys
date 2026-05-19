import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiFetch } from "../api";
import { AdminSubscriptionReminderButton } from "../components/AdminSubscriptionReminderButton";

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

export default function AdminCompanyPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const [company, setCompany] = useState<Company | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [users, setUsers] = useState<{ id: number; email: string; name: string | null }[]>([]);
  const [plan, setPlan] = useState("basic");
  const [extendDays, setExtendDays] = useState(30);
  const [msg, setMsg] = useState<string | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteErr, setDeleteErr] = useState<string | null>(null);

  const loadCore = useCallback(async () => {
    if (!id) return;
    const cid = Number(id);
    const [c, u, usr] = await Promise.all([
      apiFetch<Company>(`/admin/companies/${cid}`, { token: "admin" }),
      apiFetch<Usage>(`/admin/companies/${cid}/usage`, { token: "admin" }),
      apiFetch<{ id: number; email: string; name: string | null }[]>(`/admin/companies/${cid}/users`, {
        token: "admin",
      }),
    ]);
    setCompany(c);
    setUsage(u);
    setUsers(usr);
    setPlan(c.plan_type);
  }, [id]);

  useEffect(() => {
    const t = localStorage.getItem("fir_admin_token");
    if (!t) {
      nav("/login");
      return;
    }
    loadCore().catch(() => nav("/login"));
  }, [id, nav, loadCore]);

  async function load() {
    await loadCore();
  }

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
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <h2 className="text-lg font-semibold text-white sm:pt-1">Actions</h2>
          <div className="flex flex-wrap items-start gap-2 sm:justify-end">
            <AdminSubscriptionReminderButton companyId={Number(id)} />
            <Link
              to={`/admin/companies/${id}/fir-intelligence`}
              className="inline-flex h-10 shrink-0 items-center justify-center rounded-lg border border-brand-600/50 bg-brand-600/10 px-4 text-sm font-medium text-brand-400 hover:bg-brand-600/20"
            >
              FIR intelligence
            </Link>
          </div>
        </div>
        <form
          className="grid grid-cols-1 gap-3 sm:grid-cols-[minmax(12rem,16rem)_auto] sm:items-end sm:gap-x-3"
          onSubmit={activate}
        >
          <div className="min-w-0">
            <label className="block text-xs text-slate-500">Plan on activate</label>
            <select
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
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
            className="h-10 w-full rounded-lg bg-emerald-600 px-4 text-sm font-semibold text-white hover:bg-emerald-500 sm:w-auto sm:self-end sm:justify-self-start"
          >
            Activate subscription
          </button>
        </form>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-[minmax(12rem,16rem)_auto] sm:items-end sm:gap-x-3">
          <div className="min-w-0">
            <label className="block text-xs text-slate-500">Extend (days)</label>
            <input
              type="number"
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
              value={extendDays}
              onChange={(e) => setExtendDays(Number(e.target.value))}
            />
          </div>
          <button
            type="button"
            className="h-10 w-full rounded-lg border border-slate-600 px-4 text-sm text-slate-100 hover:bg-slate-800 sm:w-auto sm:self-end sm:justify-self-start"
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
          Removes this company from the admin list and deletes all related workspace data. Use this after offboarding a customer. To remove only
          sign-in accounts, use{" "}
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
    </div>
  );
}
