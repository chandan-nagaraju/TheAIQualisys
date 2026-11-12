import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiFetch } from "../api";
import AdminBillingShell from "../components/AdminBillingShell";

export type AdminBillingPayment = {
  id: number;
  payment_code: string | null;
  company_id: number;
  user_id: number | null;
  customer_id: number | null;
  customer_name: string | null;
  company_name: string | null;
  email: string | null;
  phone: string | null;
  billing_address: string | null;
  city: string | null;
  state: string | null;
  state_code: string | null;
  pincode: string | null;
  gstin: string | null;
  module_key: string | null;
  module_label: string | null;
  subscription_plan: string;
  plan_type: string | null;
  plan_id: number | null;
  billing_period: string | null;
  billing_period_label: string | null;
  subscription_duration: string | null;
  subscription_start: string | null;
  subscription_end: string | null;
  subscription_start_date?: string | null;
  subscription_end_date?: string | null;
  amount_inr: number;
  currency: string | null;
  original_plan_price: number | null;
  payment_method: string;
  reference_note: string | null;
  payment_date: string | null;
  payment_submitted_at: string | null;
  status: string;
  has_proof: boolean;
  pricing_snapshot: Record<string, unknown> | null;
  verified_at: string | null;
  payment_verified_at?: string | null;
  rejected_at: string | null;
  rejection_reason: string | null;
  rejection_reason_label: string | null;
  whatsapp_number: string | null;
  invoice_id?: number | null;
  invoice_number?: string | null;
  invoice_status?: string | null;
};

type ListResponse = {
  pending_count: number;
  verified_count: number;
  rejected_count: number;
  items: AdminBillingPayment[];
};

type StatusFilter = "all" | "pending_verification" | "verified" | "rejected";

export function isPendingStatus(status: string) {
  return status === "pending_verification" || status === "pending";
}

export function statusLabel(status: string) {
  if (isPendingStatus(status)) return "PENDING VERIFICATION";
  if (status === "verified") return "VERIFIED";
  if (status === "rejected") return "REJECTED";
  return status.replace(/_/g, " ").toUpperCase();
}

export function statusClass(status: string) {
  if (isPendingStatus(status)) return "bg-amber-100 text-amber-800";
  if (status === "verified") return "bg-emerald-100 text-emerald-800";
  if (status === "rejected") return "bg-red-100 text-red-800";
  return "bg-slate-200 text-slate-800";
}

export function formatWhen(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

export function formatDateOnly(iso: string | null | undefined) {
  if (!iso) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return formatWhen(iso);
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])).toLocaleDateString();
}

function paymentDateValue(iso: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toISOString().slice(0, 10);
}

function norm(s: string) {
  return s.toLowerCase().trim();
}

export default function AdminBillingPaymentsPage() {
  const nav = useNavigate();
  const [data, setData] = useState<ListResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    if (!localStorage.getItem("fir_admin_token")) {
      nav("/login");
      return;
    }
    let cancelled = false;
    (async () => {
      setErr(null);
      try {
        const res = await apiFetch<ListResponse>("/admin/billing/payments", { token: "admin" });
        if (!cancelled) setData(res);
      } catch (e) {
        if (!cancelled) setErr(e instanceof Error ? e.message : "Failed to load payments");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [nav, reloadTick]);

  const needle = norm(q);
  const rows = useMemo(() => {
    const items = data?.items ?? [];
    return items.filter((r) => {
      if (status === "pending_verification" && !isPendingStatus(r.status)) return false;
      if (status !== "all" && status !== "pending_verification" && r.status !== status) return false;
      const day = paymentDateValue(r.payment_submitted_at || r.payment_date);
      if (fromDate && day && day < fromDate) return false;
      if (toDate && day && day > toDate) return false;
      if (!needle) return true;
      return (
        String(r.id).includes(needle) ||
        norm(r.payment_code || "").includes(needle) ||
        norm(r.customer_name || "").includes(needle) ||
        norm(r.email || "").includes(needle) ||
        norm(r.company_name || "").includes(needle) ||
        norm(r.reference_note || "").includes(needle) ||
        norm(r.module_label || "").includes(needle) ||
        norm(r.module_key || "").includes(needle)
      );
    });
  }, [data, needle, status, fromDate, toDate]);

  return (
    <AdminBillingShell
      title="Payment Verification"
      description="Review and verify customer payments before activating their subscription and generating an invoice."
    >
      {err && (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <p className="text-sm text-red-400">{err}</p>
          <button
            type="button"
            className="shrink-0 rounded-lg border border-slate-600 px-3 py-1.5 text-sm font-medium text-slate-200 hover:bg-slate-800"
            onClick={() => setReloadTick((n) => n + 1)}
          >
            Retry
          </button>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Pending Verification" value={data?.pending_count ?? 0} tone="pending" />
        <Stat label="Verified" value={data?.verified_count ?? 0} tone="verified" />
        <Stat label="Rejected" value={data?.rejected_count ?? 0} tone="rejected" />
      </div>

      <div className="flex flex-col gap-3 lg:flex-row lg:flex-wrap lg:items-end">
        <label className="block min-w-[16rem] flex-1 text-xs uppercase tracking-wide text-slate-500">
          Search
          <input
            type="search"
            placeholder="Customer, company, email, payment ID, module, reference…"
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white placeholder:text-slate-600"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </label>
        <label className="block text-xs uppercase tracking-wide text-slate-500">
          Status
          <select
            className="mt-1 block min-w-[12rem] rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
            value={status}
            onChange={(e) => setStatus(e.target.value as StatusFilter)}
          >
            <option value="all">All</option>
            <option value="pending_verification">Pending Verification</option>
            <option value="verified">Verified</option>
            <option value="rejected">Rejected</option>
          </select>
        </label>
        <label className="block text-xs uppercase tracking-wide text-slate-500">
          From
          <input
            type="date"
            className="mt-1 block rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
          />
        </label>
        <label className="block text-xs uppercase tracking-wide text-slate-500">
          To
          <input
            type="date"
            className="mt-1 block rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
          />
        </label>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-800">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-slate-900/80 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-3">Payment ID</th>
              <th className="px-4 py-3">Customer</th>
              <th className="px-4 py-3">Module</th>
              <th className="px-4 py-3">Plan</th>
              <th className="px-4 py-3">Billing Period</th>
              <th className="px-4 py-3">Amount</th>
              <th className="px-4 py-3">Submitted At</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {!data && !err && (
              <tr>
                <td colSpan={9} className="px-4 py-6 text-center text-slate-500">
                  Loading payments…
                </td>
              </tr>
            )}
            {data && rows.length === 0 && (
              <tr>
                <td colSpan={9} className="px-4 py-6 text-center text-slate-500">
                  No payment records match.
                </td>
              </tr>
            )}
            {rows.map((r) => (
              <tr
                key={r.id}
                className="cursor-pointer hover:bg-slate-900/40"
                onClick={() => nav(`/admin/billing/payments/${r.id}`)}
              >
                <td className="px-4 py-3 font-mono text-slate-200">{r.payment_code || `PAY-${String(r.id).padStart(5, "0")}`}</td>
                <td className="px-4 py-3 text-slate-200">{r.customer_name || r.company_name || "—"}</td>
                <td className="px-4 py-3 text-slate-300">{r.module_label || "FIR"}</td>
                <td className="px-4 py-3 text-slate-300">{r.subscription_plan}</td>
                <td className="px-4 py-3 text-slate-300">{r.billing_period_label || r.billing_period || "—"}</td>
                <td className="px-4 py-3 text-slate-200">₹{r.amount_inr}</td>
                <td className="px-4 py-3 text-xs text-slate-400">{formatWhen(r.payment_submitted_at || r.payment_date)}</td>
                <td className="px-4 py-3">
                  <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${statusClass(r.status)}`}>
                    {statusLabel(r.status)}
                  </span>
                </td>
                <td className="px-4 py-3 text-right" onClick={(e) => e.stopPropagation()}>
                  <Link className="text-brand-600 hover:underline" to={`/admin/billing/payments/${r.id}`}>
                    View
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </AdminBillingShell>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "pending" | "verified" | "rejected";
}) {
  const colors =
    tone === "pending"
      ? "border-amber-300 bg-amber-50 text-amber-800"
      : tone === "verified"
        ? "border-emerald-300 bg-emerald-50 text-emerald-800"
        : "border-red-300 bg-red-50 text-red-800";
  const valueColor =
    tone === "pending" ? "text-amber-600" : tone === "verified" ? "text-emerald-600" : "text-red-600";
  return (
    <div className={`rounded-xl border p-4 ${colors}`}>
      <p className="text-xs font-semibold uppercase tracking-wide">{label}</p>
      <p className={`mt-1 text-2xl font-bold ${valueColor}`}>{value}</p>
    </div>
  );
}
