import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiFetch } from "../api";
import AdminBillingShell from "../components/AdminBillingShell";
import { formatDateOnly, type AdminBillingPayment } from "./AdminBillingPaymentsPage";

export type AdminBillingInvoice = {
  id: number;
  invoice_id: string | null;
  invoice_number: string;
  payment_id: number;
  payment_code: string | null;
  customer_name: string | null;
  company_name: string | null;
  module_name: string | null;
  plan_name: string;
  billing_period: string | null;
  billing_period_label: string | null;
  invoice_date: string | null;
  subscription_start_date: string | null;
  subscription_end_date: string | null;
  amount?: number;
  grand_total: number;
  taxable_amount: number;
  cgst: number;
  sgst: number;
  igst: number;
  total_tax: number;
  currency: string | null;
  tax_mode: string | null;
  cgst_rate: number | null;
  sgst_rate: number | null;
  igst_rate: number | null;
  status: string;
  payment_method: string | null;
  payment_reference: string | null;
  payment_verified_at: string | null;
  line_description: string | null;
  email: string | null;
  phone: string | null;
  billing_address: string | null;
  city: string | null;
  state: string | null;
  state_code: string | null;
  pincode: string | null;
  gstin: string | null;
  seller?: Record<string, unknown> | null;
  vendor_code?: string | null;
  hsn_sac?: string | null;
};

type ListResponse = {
  total_count: number;
  draft_count: number;
  generated_count: number;
  cancelled_count: number;
  items: AdminBillingInvoice[];
};

export function formatInr(n: number | null | undefined) {
  const v = Number(n || 0);
  return `₹${v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function invoiceStatusClass(status: string) {
  if (status === "generated") return "bg-emerald-100 text-emerald-800";
  if (status === "cancelled") return "bg-red-100 text-red-800";
  return "bg-slate-200 text-slate-800";
}

export default function AdminBillingInvoicesPage() {
  const nav = useNavigate();
  const [data, setData] = useState<ListResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [payments, setPayments] = useState<AdminBillingPayment[]>([]);
  const [pick, setPick] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    const [inv, pay] = await Promise.all([
      apiFetch<ListResponse>("/admin/billing/invoices", { token: "admin" }),
      apiFetch<{ items: AdminBillingPayment[] }>("/admin/billing/payments?status=verified", { token: "admin" }),
    ]);
    setData(inv);
    setPayments(pay.items || []);
  }

  useEffect(() => {
    if (!localStorage.getItem("fir_admin_token")) {
      nav("/login");
      return;
    }
    load().catch((e) => setErr(e instanceof Error ? e.message : "Failed to load invoices"));
  }, [nav]);

  const eligible = useMemo(
    () => payments.filter((p) => p.status === "verified" && !p.invoice_id),
    [payments],
  );

  async function generate() {
    if (!pick) return;
    setBusy(true);
    setErr(null);
    try {
      const preview = await apiFetch<AdminBillingInvoice>("/admin/billing/invoices/preview", {
        method: "POST",
        token: "admin",
        body: JSON.stringify({ payment_id: Number(pick) }),
      });
      const ok = window.confirm(
        `Generate invoice for this verified payment?\n${preview.customer_name}\n${preview.module_name} · ${preview.plan_name} · ${preview.billing_period_label}\nGrand total ${formatInr(preview.grand_total)}`,
      );
      if (!ok) return;
      const created = await apiFetch<AdminBillingInvoice>("/admin/billing/invoices", {
        method: "POST",
        token: "admin",
        body: JSON.stringify({ payment_id: Number(pick) }),
      });
      nav(`/admin/billing/invoices/${created.id}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Generate failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AdminBillingShell
      title="Invoices"
      description="View and manage invoices generated for verified customer payments."
    >
      {err && <p className="text-sm text-red-400">{err}</p>}
      <div className="grid gap-3 sm:grid-cols-4">
        <Stat label="Total Invoices" value={data?.total_count ?? 0} />
        <Stat label="Draft" value={data?.draft_count ?? 0} />
        <Stat label="Generated" value={data?.generated_count ?? 0} />
        <Stat label="Cancelled" value={data?.cancelled_count ?? 0} />
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-xs uppercase text-slate-500">
          Generate Invoice
          <select
            className="mt-1 block min-w-[280px] rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
            value={pick}
            onChange={(e) => setPick(e.target.value)}
          >
            <option value="">Select verified payment…</option>
            {eligible.map((p) => (
              <option key={p.id} value={p.id}>
                {p.payment_code || `PAY-${p.id}`} · {p.company_name} · ₹{p.amount_inr}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="rounded-lg bg-emerald-700 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
          disabled={!pick || busy}
          onClick={() => void generate()}
        >
          Generate Invoice
        </button>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-800">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-slate-900/80 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-3">Invoice Number</th>
              <th className="px-4 py-3">Customer</th>
              <th className="px-4 py-3">Company</th>
              <th className="px-4 py-3">Module</th>
              <th className="px-4 py-3">Plan</th>
              <th className="px-4 py-3">Billing Period</th>
              <th className="px-4 py-3">Invoice Date</th>
              <th className="px-4 py-3">Amount</th>
              <th className="px-4 py-3">Payment ID</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {!data && !err && (
              <tr>
                <td colSpan={11} className="px-4 py-6 text-center text-slate-500">
                  Loading invoices…
                </td>
              </tr>
            )}
            {data && data.items.length === 0 && (
              <tr>
                <td colSpan={11} className="px-4 py-6 text-center text-slate-500">
                  No invoices yet.
                </td>
              </tr>
            )}
            {data?.items.map((r) => (
              <tr key={r.id} className="cursor-pointer hover:bg-slate-900/40" onClick={() => nav(`/admin/billing/invoices/${r.id}`)}>
                <td className="px-4 py-3 font-mono text-slate-200">{r.invoice_number}</td>
                <td className="px-4 py-3 text-slate-200">{r.customer_name || "—"}</td>
                <td className="px-4 py-3 text-slate-300">{r.company_name || "—"}</td>
                <td className="px-4 py-3 text-slate-300">{r.module_name || "—"}</td>
                <td className="px-4 py-3 text-slate-300">{r.plan_name}</td>
                <td className="px-4 py-3 text-slate-300">{r.billing_period_label || r.billing_period || "—"}</td>
                <td className="px-4 py-3 text-slate-300">{formatDateOnly(r.invoice_date)}</td>
                <td className="px-4 py-3 text-slate-200">{formatInr(r.grand_total)}</td>
                <td className="px-4 py-3 font-mono text-slate-300">{r.payment_code || r.payment_id}</td>
                <td className="px-4 py-3">
                  <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${invoiceStatusClass(r.status)}`}>
                    {r.status.toUpperCase()}
                  </span>
                </td>
                <td className="px-4 py-3 text-right" onClick={(e) => e.stopPropagation()}>
                  <Link className="text-brand-600 hover:underline" to={`/admin/billing/invoices/${r.id}`}>
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

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-900">{value}</p>
    </div>
  );
}
