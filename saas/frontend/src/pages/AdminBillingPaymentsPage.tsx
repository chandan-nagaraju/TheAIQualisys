import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiFetch } from "../api";
import AdminBillingShell from "../components/AdminBillingShell";

export type AdminBillingPayment = {
  id: number;
  company_id: number;
  user_id: number | null;
  customer_name: string | null;
  company_name: string | null;
  email: string | null;
  phone: string | null;
  subscription_plan: string;
  subscription_start: string | null;
  subscription_end: string | null;
  amount_inr: number;
  payment_method: string;
  reference_note: string | null;
  payment_date: string | null;
  status: string;
  has_proof: boolean;
};

type ListResponse = {
  pending_count: number;
  verified_count: number;
  rejected_count: number;
  items: AdminBillingPayment[];
};

type StatusFilter = "all" | "pending" | "verified" | "rejected";

function norm(s: string) {
  return s.toLowerCase().trim();
}

function statusLabel(status: string) {
  if (status === "pending") return "PENDING";
  if (status === "verified") return "VERIFIED";
  if (status === "rejected") return "REJECTED";
  return status.toUpperCase();
}

function statusClass(status: string) {
  if (status === "pending") return "bg-amber-500/15 text-amber-300";
  if (status === "verified") return "bg-emerald-500/15 text-emerald-300";
  if (status === "rejected") return "bg-red-500/15 text-red-300";
  return "bg-slate-700/40 text-slate-300";
}

function formatWhen(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

function paymentDateValue(iso: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toISOString().slice(0, 10);
}

export default function AdminBillingPaymentsPage() {
  const nav = useNavigate();
  const [data, setData] = useState<ListResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");

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
  }, [nav]);

  const needle = norm(q);
  const rows = useMemo(() => {
    const items = data?.items ?? [];
    return items.filter((r) => {
      if (status !== "all" && r.status !== status) return false;
      const day = paymentDateValue(r.payment_date);
      if (fromDate && day && day < fromDate) return false;
      if (toDate && day && day > toDate) return false;
      if (!needle) return true;
      return (
        String(r.id).includes(needle) ||
        norm(r.customer_name || "").includes(needle) ||
        norm(r.email || "").includes(needle) ||
        norm(r.company_name || "").includes(needle) ||
        norm(r.reference_note || "").includes(needle)
      );
    });
  }, [data, needle, status, fromDate, toDate]);

  return (
    <AdminBillingShell
      title="Payment Verification"
      description="Review and verify customer payments before activating their subscription and generating an invoice."
    >
      {err && <p className="text-sm text-red-400">{err}</p>}

      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Pending Payments" value={data?.pending_count ?? 0} />
        <Stat label="Verified Payments" value={data?.verified_count ?? 0} />
        <Stat label="Rejected Payments" value={data?.rejected_count ?? 0} />
      </div>

      <div className="flex flex-col gap-3 lg:flex-row lg:flex-wrap lg:items-end">
        <label className="block min-w-[16rem] flex-1 text-xs uppercase tracking-wide text-slate-500">
          Search
          <input
            type="search"
            placeholder="Customer, email, payment ID, reference…"
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white placeholder:text-slate-600"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </label>
        <label className="block text-xs uppercase tracking-wide text-slate-500">
          Status
          <select
            className="mt-1 block min-w-[10rem] rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
            value={status}
            onChange={(e) => setStatus(e.target.value as StatusFilter)}
          >
            <option value="all">All</option>
            <option value="pending">Pending</option>
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
              <th className="px-4 py-3">Email</th>
              <th className="px-4 py-3">Subscription Plan</th>
              <th className="px-4 py-3">Amount</th>
              <th className="px-4 py-3">Payment Date</th>
              <th className="px-4 py-3">Payment Method</th>
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
                  No payment records match. SaaS upgrades currently complete via UPI/WhatsApp and are not stored as
                  payment rows yet.
                </td>
              </tr>
            )}
            {rows.map((r) => (
              <tr
                key={r.id}
                className="cursor-pointer hover:bg-slate-900/40"
                onClick={() => nav(`/admin/billing/payments/${r.id}`)}
              >
                <td className="px-4 py-3 font-mono text-slate-200">{r.id}</td>
                <td className="px-4 py-3 text-slate-200">{r.customer_name || r.company_name || "—"}</td>
                <td className="px-4 py-3 font-mono text-slate-400">{r.email || "—"}</td>
                <td className="px-4 py-3 text-slate-300">{r.subscription_plan}</td>
                <td className="px-4 py-3 text-slate-200">₹{r.amount_inr}</td>
                <td className="px-4 py-3 text-xs text-slate-400">{formatWhen(r.payment_date)}</td>
                <td className="px-4 py-3 text-slate-300">{r.payment_method}</td>
                <td className="px-4 py-3">
                  <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${statusClass(r.status)}`}>
                    {statusLabel(r.status)}
                  </span>
                </td>
                <td className="px-4 py-3 text-right" onClick={(e) => e.stopPropagation()}>
                  <PaymentActions payment={r} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </AdminBillingShell>
  );
}

export function PaymentActions({ payment }: { payment: AdminBillingPayment }) {
  const coming = "Payment verification workflow comes in the next step";
  return (
    <div className="inline-flex flex-wrap items-center justify-end gap-3">
      {payment.status === "pending" && (
        <>
          <button type="button" disabled title={coming} className="text-emerald-300/50 disabled:cursor-not-allowed">
            Verify Payment
          </button>
          <button type="button" disabled title={coming} className="text-red-400/50 disabled:cursor-not-allowed">
            Reject Payment
          </button>
        </>
      )}
      {payment.status === "verified" && (
        <button type="button" disabled title="Invoice generation is not implemented yet" className="text-slate-500 disabled:cursor-not-allowed">
          View Invoice
        </button>
      )}
      <Link className="text-brand-600 hover:underline" to={`/admin/billing/payments/${payment.id}`}>
        {payment.status === "rejected" ? "View Details" : "Details"}
      </Link>
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
