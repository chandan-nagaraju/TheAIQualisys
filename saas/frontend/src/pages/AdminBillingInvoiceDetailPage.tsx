import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiFetch, apiUrl } from "../api";
import AdminBillingShell from "../components/AdminBillingShell";
import { formatDateOnly, formatWhen } from "./AdminBillingPaymentsPage";
import { formatInr, invoiceStatusClass, type AdminBillingInvoice } from "./AdminBillingInvoicesPage";

function dmy(iso: string | null | undefined) {
  if (!iso) return "";
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "2-digit", timeZone: "UTC" });
}

function amt(n: number | null | undefined) {
  return Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const ONES = [
  "",
  "One",
  "Two",
  "Three",
  "Four",
  "Five",
  "Six",
  "Seven",
  "Eight",
  "Nine",
  "Ten",
  "Eleven",
  "Twelve",
  "Thirteen",
  "Fourteen",
  "Fifteen",
  "Sixteen",
  "Seventeen",
  "Eighteen",
  "Nineteen",
];
const TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"];

function two(n: number) {
  if (n < 20) return ONES[n];
  return `${TENS[Math.floor(n / 10)]} ${ONES[n % 10]}`.trim();
}

function amountInWords(raw: number | null | undefined) {
  const n = Math.round(Number(raw || 0) * 100) / 100;
  const rupees = Math.floor(n);
  const paise = Math.round((n - rupees) * 100);
  let rem = rupees;
  const crore = Math.floor(rem / 10000000);
  rem %= 10000000;
  const lakh = Math.floor(rem / 100000);
  rem %= 100000;
  const thousand = Math.floor(rem / 1000);
  rem %= 1000;
  const hundred = Math.floor(rem / 100);
  rem %= 100;
  const parts: string[] = [];
  if (crore) parts.push(`${two(crore)} Crore`);
  if (lakh) parts.push(`${two(lakh)} Lakh`);
  if (thousand) parts.push(`${two(thousand)} Thousand`);
  if (hundred) parts.push(`${ONES[hundred]} Hundred`);
  if (rem) parts.push(two(rem));
  let words = `Indian Rupees ${parts.join(" ") || "Zero"}`;
  if (paise) words += ` and ${two(paise)} Paise`;
  return `${words} Only`;
}

function partyBlock(title: string, row: AdminBillingInvoice) {
  return (
    <td className="align-top p-2 w-1/2">
      <div className="text-[10px] font-semibold">{title}</div>
      <div className="font-semibold">{row.company_name || row.customer_name}</div>
      <div className="whitespace-pre-line">{row.billing_address}</div>
      <div>
        {[row.city, row.pincode].filter(Boolean).join(" ")}
      </div>
      <div>GSTIN/UIN : {row.gstin || "—"}</div>
      <div>
        State Name : {row.state || "—"} , Code : {row.state_code || "—"}
      </div>
    </td>
  );
}

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
  const cgstSgst = row?.tax_mode === "cgst_sgst";

  return (
    <AdminBillingShell title="Invoice">
      <Link to="/admin/billing/invoices" className="text-sm text-brand-500 hover:underline print:hidden">
        ← Invoices
      </Link>
      {err && <p className="text-sm text-red-400 print:hidden">{err}</p>}
      {!row && !err && <p className="text-sm text-slate-400">Loading invoice…</p>}
      {row && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
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
                Download PDF
              </button>
              <button type="button" className="rounded-lg border border-slate-600 px-3 py-1.5 text-sm text-slate-200" onClick={() => window.print()}>
                Print
              </button>
            </div>
          </div>

          <div className="overflow-x-auto rounded-xl border border-slate-800 bg-white p-3 text-[11px] leading-snug text-slate-900 print:border-0 print:p-0">
            <table className="w-full border-collapse border border-slate-800">
              <tbody>
                <tr>
                  <td colSpan={4} className="border border-slate-800 py-2 text-center text-base font-bold">
                    TAX INVOICE
                  </td>
                </tr>
                <tr>
                  <td className="border border-slate-800 p-2 align-top" colSpan={2}>
                    <div className="text-sm font-bold">{seller.business_name || "TheAIQualisys"}</div>
                    <div className="whitespace-pre-line">{seller.business_address || ""}</div>
                    <div>GSTIN/UIN: {seller.gstin || "—"}</div>
                    <div>
                      State Name : {seller.state || "—"} , Code : {seller.state_code || "—"}
                    </div>
                    {(seller.email || seller.phone) && (
                      <div>
                        E-Mail : {seller.email || "—"}  Ph: {seller.phone || "—"}
                      </div>
                    )}
                  </td>
                  <td className="border border-slate-800 p-0 align-top" colSpan={2}>
                    <table className="w-full border-collapse">
                      <tbody>
                        <Meta label="Invoice No." value={row.invoice_number} label2="Dated" value2={dmy(row.invoice_date)} />
                        <Meta label="Delivery Note" value="" label2="Mode/Terms of Payment" value2={row.payment_method || "UPI"} />
                        <Meta
                          label="Reference No. & Date."
                          value={row.payment_code || ""}
                          label2="Other References"
                          value2=""
                        />
                        <Meta label="Buyer's Order No." value="" label2="Dated" value2="" />
                        <Meta label="Dispatch Doc No." value="" label2="Delivery Note Date" value2="" />
                        <Meta label="Dispatched through" value="" label2="Destination" value2="" />
                        <Meta
                          label="Supplier / Vendor Code"
                          value={(row as AdminBillingInvoice & { vendor_code?: string }).vendor_code || ""}
                          label2="Terms of Delivery"
                          value2={`${row.billing_period_label || ""} ${dmy(row.subscription_start_date)} to ${dmy(row.subscription_end_date)}`.trim()}
                        />
                      </tbody>
                    </table>
                  </td>
                </tr>
                <tr>
                  {partyBlock("Consignee (Ship to)", row)}
                  {partyBlock("Buyer (Bill to)", row)}
                </tr>
              </tbody>
            </table>

            <table className="mt-0 w-full border-collapse border border-slate-800 text-center">
              <thead>
                <tr className="font-semibold">
                  <th className="border border-slate-800 p-1">SI</th>
                  <th className="border border-slate-800 p-1 text-left">Description of Services</th>
                  <th className="border border-slate-800 p-1">HSN/SAC</th>
                  <th className="border border-slate-800 p-1">Quantity</th>
                  <th className="border border-slate-800 p-1">Rate</th>
                  <th className="border border-slate-800 p-1">per</th>
                  <th className="border border-slate-800 p-1">Amount</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="border border-slate-800 p-1">1</td>
                  <td className="border border-slate-800 p-1 text-left">{row.line_description}</td>
                  <td className="border border-slate-800 p-1">{(row as AdminBillingInvoice & { hsn_sac?: string }).hsn_sac || "998314"}</td>
                  <td className="border border-slate-800 p-1">1 Nos</td>
                  <td className="border border-slate-800 p-1 text-right">{amt(row.taxable_amount)}</td>
                  <td className="border border-slate-800 p-1">Nos</td>
                  <td className="border border-slate-800 p-1 text-right">{amt(row.taxable_amount)}</td>
                </tr>
                {cgstSgst ? (
                  <>
                    <tr>
                      <td className="border border-slate-800 p-1" />
                      <td className="border border-slate-800 p-1 text-right">CGST @ {row.cgst_rate}%</td>
                      <td className="border border-slate-800 p-1" colSpan={4} />
                      <td className="border border-slate-800 p-1 text-right">{amt(row.cgst)}</td>
                    </tr>
                    <tr>
                      <td className="border border-slate-800 p-1" />
                      <td className="border border-slate-800 p-1 text-right">SGST @ {row.sgst_rate}%</td>
                      <td className="border border-slate-800 p-1" colSpan={4} />
                      <td className="border border-slate-800 p-1 text-right">{amt(row.sgst)}</td>
                    </tr>
                  </>
                ) : (
                  <tr>
                    <td className="border border-slate-800 p-1" />
                    <td className="border border-slate-800 p-1 text-right">IGST @ {row.igst_rate}%</td>
                    <td className="border border-slate-800 p-1" colSpan={4} />
                    <td className="border border-slate-800 p-1 text-right">{amt(row.igst)}</td>
                  </tr>
                )}
                <tr className="font-semibold">
                  <td className="border border-slate-800 p-1" />
                  <td className="border border-slate-800 p-1 text-left">Total</td>
                  <td className="border border-slate-800 p-1" />
                  <td className="border border-slate-800 p-1">1 Nos</td>
                  <td className="border border-slate-800 p-1" colSpan={2} />
                  <td className="border border-slate-800 p-1 text-right">{amt(row.grand_total)}</td>
                </tr>
                <tr>
                  <td className="border border-slate-800 p-2 text-left" colSpan={6}>
                    Amount Chargeable (in words)
                    <div className="font-semibold">{amountInWords(row.grand_total)}</div>
                  </td>
                  <td className="border border-slate-800 p-2 text-right align-top">E. &amp; O.E</td>
                </tr>
              </tbody>
            </table>

            <table className="w-full border-collapse border border-slate-800 text-center">
              <thead>
                <tr className="font-semibold">
                  <th className="border border-slate-800 p-1">HSN/SAC</th>
                  <th className="border border-slate-800 p-1">Taxable Value</th>
                  {cgstSgst ? (
                    <>
                      <th className="border border-slate-800 p-1">CGST Rate</th>
                      <th className="border border-slate-800 p-1">CGST Amount</th>
                      <th className="border border-slate-800 p-1">SGST Rate</th>
                      <th className="border border-slate-800 p-1">SGST Amount</th>
                    </>
                  ) : (
                    <>
                      <th className="border border-slate-800 p-1">IGST Rate</th>
                      <th className="border border-slate-800 p-1">IGST Amount</th>
                    </>
                  )}
                  <th className="border border-slate-800 p-1">Total Tax Amount</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="border border-slate-800 p-1">{(row as AdminBillingInvoice & { hsn_sac?: string }).hsn_sac || "998314"}</td>
                  <td className="border border-slate-800 p-1">{amt(row.taxable_amount)}</td>
                  {cgstSgst ? (
                    <>
                      <td className="border border-slate-800 p-1">{row.cgst_rate}%</td>
                      <td className="border border-slate-800 p-1">{amt(row.cgst)}</td>
                      <td className="border border-slate-800 p-1">{row.sgst_rate}%</td>
                      <td className="border border-slate-800 p-1">{amt(row.sgst)}</td>
                    </>
                  ) : (
                    <>
                      <td className="border border-slate-800 p-1">{row.igst_rate}%</td>
                      <td className="border border-slate-800 p-1">{amt(row.igst)}</td>
                    </>
                  )}
                  <td className="border border-slate-800 p-1">{amt(row.total_tax)}</td>
                </tr>
              </tbody>
            </table>

            <table className="w-full border-collapse border border-slate-800">
              <tbody>
                <tr>
                  <td className="border border-slate-800 p-2 align-top w-1/2">
                    <div className="font-semibold">Declaration</div>
                    <p className="mt-1">
                      We declare that this invoice shows the actual price of the services described and that all
                      particulars are true and correct.
                    </p>
                    <p className="mt-6">Customer's Seal and Signature</p>
                  </td>
                  <td className="border border-slate-800 p-2 align-top text-right w-1/2">
                    <div className="font-semibold">for {seller.business_name || "TheAIQualisys"}</div>
                    <p className="mt-10">Authorised Signatory</p>
                  </td>
                </tr>
              </tbody>
            </table>
            <p className="mt-2 text-center text-[10px] font-semibold">
              SUBJECT TO {(seller.city || seller.state || "INDIA").toString().toUpperCase()} JURISDICTION
            </p>
            <p className="mt-2 print:hidden text-slate-500">
              Payment{" "}
              <Link className="text-brand-600 hover:underline" to={`/admin/billing/payments/${row.payment_id}`}>
                {row.payment_code || `PAY-${row.payment_id}`}
              </Link>{" "}
              · verified {formatWhen(row.payment_verified_at)} · invoice date {formatDateOnly(row.invoice_date)} ·{" "}
              {formatInr(row.grand_total)}
            </p>
          </div>
        </div>
      )}
    </AdminBillingShell>
  );
}

function Meta({
  label,
  value,
  label2,
  value2,
}: {
  label: string;
  value: string;
  label2: string;
  value2: string;
}) {
  return (
    <tr>
      <td className="border border-slate-800 p-1 align-top w-1/2">
        <div className="text-[9px] text-slate-500">{label}</div>
        <div className="font-semibold">{value || "\u00a0"}</div>
      </td>
      <td className="border border-slate-800 p-1 align-top w-1/2">
        <div className="text-[9px] text-slate-500">{label2}</div>
        <div className="font-semibold">{value2 || "\u00a0"}</div>
      </td>
    </tr>
  );
}
