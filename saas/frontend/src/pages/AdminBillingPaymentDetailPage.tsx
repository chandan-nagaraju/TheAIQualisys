import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiFetch } from "../api";
import AdminBillingShell from "../components/AdminBillingShell";
import { PaymentActions, type AdminBillingPayment } from "./AdminBillingPaymentsPage";

function formatWhen(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

function formatDay(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(`${iso}T12:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString();
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

export default function AdminBillingPaymentDetailPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const [row, setRow] = useState<AdminBillingPayment | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!localStorage.getItem("fir_admin_token")) {
      nav("/login");
      return;
    }
    if (!id) return;
    let cancelled = false;
    (async () => {
      setErr(null);
      try {
        const res = await apiFetch<AdminBillingPayment>(`/admin/billing/payments/${id}`, { token: "admin" });
        if (!cancelled) setRow(res);
      } catch (e) {
        if (!cancelled) setErr(e instanceof Error ? e.message : "Failed to load payment");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id, nav]);

  return (
    <AdminBillingShell title="Payment details">
      <Link to="/admin/billing/payments" className="text-sm text-brand-500 hover:underline">
        ← Payments
      </Link>
      {err && <p className="text-sm text-red-400">{err}</p>}
      {!row && !err && <p className="text-sm text-slate-400">Loading payment…</p>}
      {row && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${statusClass(row.status)}`}>
              {statusLabel(row.status)}
            </span>
            <PaymentActions payment={row} />
          </div>
          <div className="overflow-x-auto rounded-xl border border-slate-800">
            <table className="min-w-full text-left text-sm">
              <tbody className="divide-y divide-slate-800">
                <DetailRow label="Payment ID" value={String(row.id)} mono />
                <DetailRow label="Customer name" value={row.customer_name || "—"} />
                <DetailRow label="Company name" value={row.company_name || "—"} />
                <DetailRow label="Email" value={row.email || "—"} mono />
                <DetailRow label="Phone" value={row.phone || "—"} />
                <DetailRow label="Subscription plan" value={row.subscription_plan} />
                <DetailRow label="Subscription start date" value={formatDay(row.subscription_start)} />
                <DetailRow label="Subscription end date" value={formatDay(row.subscription_end)} />
                <DetailRow label="Amount" value={`₹${row.amount_inr}`} />
                <DetailRow label="Payment method" value={row.payment_method} />
                <DetailRow label="Transaction / payment reference" value={row.reference_note || "—"} mono />
                <DetailRow label="Payment date" value={formatWhen(row.payment_date)} />
                <DetailRow label="Payment proof" value={row.has_proof ? "Uploaded" : "Not uploaded"} />
                <DetailRow label="Current status" value={statusLabel(row.status)} />
              </tbody>
            </table>
          </div>
          {row.company_id ? (
            <Link className="text-sm text-brand-600 hover:underline" to={`/admin/companies/${row.company_id}`}>
              Open company
            </Link>
          ) : null}
        </div>
      )}
    </AdminBillingShell>
  );
}

function DetailRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <tr>
      <th className="w-64 bg-slate-900/80 px-4 py-3 text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </th>
      <td className={`px-4 py-3 text-slate-200 ${mono ? "font-mono text-slate-300" : ""}`}>{value}</td>
    </tr>
  );
}
