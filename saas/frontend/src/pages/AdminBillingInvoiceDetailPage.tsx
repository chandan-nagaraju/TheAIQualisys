import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiFetch, apiUrl } from "../api";
import AdminBillingShell from "../components/AdminBillingShell";
import { formatDateOnly, formatWhen } from "./AdminBillingPaymentsPage";
import { formatInr, invoiceStatusClass, type AdminBillingInvoice } from "./AdminBillingInvoicesPage";

export default function AdminBillingInvoiceDetailPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const [row, setRow] = useState<AdminBillingInvoice | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!localStorage.getItem("fir_admin_token")) {
      nav("/login");
      return;
    }
    if (!id) return;
    apiFetch<AdminBillingInvoice>(`/admin/billing/invoices/${id}`, { token: "admin" })
      .then(setRow)
      .catch((e) => setErr(e instanceof Error ? e.message : "Failed to load invoice"));
  }, [id, nav]);

  async function downloadPdf() {
    if (!row) return;
    setBusy(true);
    setErr(null);
    try {
      const token = localStorage.getItem("fir_admin_token") || "";
      const res = await fetch(apiUrl(`/admin/billing/invoices/${row.id}/pdf`), {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("PDF download failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${row.invoice_number}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "PDF failed");
    } finally {
      setBusy(false);
    }
  }

  const seller = (row?.seller || {}) as Record<string, string | undefined>;

  return (
    <AdminBillingShell title="Invoice">
      <Link to="/admin/billing/invoices" className="text-sm text-brand-500 hover:underline">
        ← Invoices
      </Link>
      {err && <p className="text-sm text-red-400">{err}</p>}
      {!row && !err && <p className="text-sm text-slate-400">Loading invoice…</p>}
      {row && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${invoiceStatusClass(row.status)}`}>
              {row.status.toUpperCase()}
            </span>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="rounded-lg bg-emerald-700 px-3 py-1.5 text-sm text-white disabled:opacity-50"
                disabled={busy}
                onClick={() => void downloadPdf()}
              >
                Generate PDF
              </button>
              <button type="button" className="rounded-lg border border-slate-600 px-3 py-1.5 text-sm text-slate-200" onClick={() => window.print()}>
                Print
              </button>
            </div>
          </div>

          <div className="rounded-xl border border-slate-800 bg-white p-6 text-slate-900 print:border-0">
            <h3 className="text-lg font-semibold">TAX INVOICE {row.invoice_number}</h3>
            <p className="text-sm text-slate-600">Invoice date: {formatDateOnly(row.invoice_date)}</p>
            <div className="mt-4 grid gap-6 md:grid-cols-2 text-sm">
              <div>
                <p className="font-semibold">Seller</p>
                <p>{seller.business_name || "—"}</p>
                <p className="whitespace-pre-line">{seller.business_address || ""}</p>
                <p>GSTIN: {seller.gstin || "—"}</p>
                <p>
                  State: {seller.state || "—"} ({seller.state_code || "—"})
                </p>
              </div>
              <div>
                <p className="font-semibold">Bill to</p>
                <p>{row.customer_name}</p>
                <p>{row.company_name}</p>
                <p>{row.billing_address || "—"}</p>
                <p>
                  {row.city || ""} {row.pincode || ""} {row.state || ""} ({row.state_code || "—"})
                </p>
                <p>GSTIN: {row.gstin || "—"}</p>
                <p>
                  {row.email || "—"} · {row.phone || "—"}
                </p>
              </div>
            </div>
            <div className="mt-4 text-sm space-y-1">
              <p>
                Payment:{" "}
                <Link className="text-brand-600 hover:underline" to={`/admin/billing/payments/${row.payment_id}`}>
                  {row.payment_code || `PAY-${row.payment_id}`}
                </Link>{" "}
                · {row.payment_method} · {row.payment_reference || "—"}
              </p>
              <p>Payment verified: {formatWhen(row.payment_verified_at)}</p>
              <p>
                Subscription period: {formatDateOnly(row.subscription_start_date)} to {formatDateOnly(row.subscription_end_date)}
              </p>
              <p>Billing period: {row.billing_period_label || row.billing_period}</p>
            </div>
            <table className="mt-4 min-w-full text-sm">
              <thead>
                <tr className="border-b text-left">
                  <th className="py-2">Description</th>
                  <th>Qty</th>
                  <th>Rate</th>
                  <th>Amount</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-b">
                  <td className="py-2">{row.line_description}</td>
                  <td>1</td>
                  <td>{formatInr(row.taxable_amount)}</td>
                  <td>{formatInr(row.taxable_amount)}</td>
                </tr>
              </tbody>
            </table>
            <div className="mt-4 ml-auto max-w-xs text-sm space-y-1">
              <Row label="Taxable value" value={formatInr(row.taxable_amount)} />
              {row.tax_mode === "cgst_sgst" ? (
                <>
                  <Row label={`CGST @ ${row.cgst_rate}%`} value={formatInr(row.cgst)} />
                  <Row label={`SGST @ ${row.sgst_rate}%`} value={formatInr(row.sgst)} />
                </>
              ) : (
                <Row label={`IGST @ ${row.igst_rate}%`} value={formatInr(row.igst)} />
              )}
              <Row label="Total tax" value={formatInr(row.total_tax)} />
              <Row label="Grand total" value={formatInr(row.grand_total)} strong />
            </div>
          </div>
        </div>
      )}
    </AdminBillingShell>
  );
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className={`flex justify-between ${strong ? "font-semibold" : ""}`}>
      <span>{label}</span>
      <span>{value}</span>
    </div>
  );
}
