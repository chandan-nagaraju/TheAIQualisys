import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiFetch } from "../api";
import AdminBillingShell from "../components/AdminBillingShell";
import {
  formatDateOnly,
  formatWhen,
  isPendingStatus,
  statusClass,
  statusLabel,
  type AdminBillingPayment,
} from "./AdminBillingPaymentsPage";

const REJECT_REASONS = [
  { value: "payment_not_received", label: "Payment not received" },
  { value: "incorrect_amount", label: "Incorrect amount" },
  { value: "screenshot_mismatch", label: "Screenshot does not match" },
  { value: "transaction_not_found", label: "Transaction not found" },
  { value: "wrong_account", label: "Wrong account" },
  { value: "other", label: "Other" },
] as const;

export default function AdminBillingPaymentDetailPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const [row, setRow] = useState<AdminBillingPayment | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [verifyOpen, setVerifyOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState<(typeof REJECT_REASONS)[number]["value"]>("payment_not_received");
  const [rejectNote, setRejectNote] = useState("");
  const [busy, setBusy] = useState(false);

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

  async function confirmVerify() {
    if (!row) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await apiFetch<AdminBillingPayment>(`/admin/billing/payments/${row.id}/verify`, {
        method: "POST",
        token: "admin",
        body: "{}",
      });
      setRow(res);
      setVerifyOpen(false);
      setMsg("Payment verified. Subscription dates are set from this verification. Invoice is not generated yet.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Verify failed");
    } finally {
      setBusy(false);
    }
  }

  async function confirmReject() {
    if (!row) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await apiFetch<AdminBillingPayment>(`/admin/billing/payments/${row.id}/reject`, {
        method: "POST",
        token: "admin",
        body: JSON.stringify({ reason: rejectReason, note: rejectNote || null }),
      });
      setRow(res);
      setRejectOpen(false);
      setMsg("Payment rejected. Subscription was not activated.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Reject failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AdminBillingShell title="Payment details">
      <Link to="/admin/billing/payments" className="text-sm text-brand-500 hover:underline">
        ← Payments
      </Link>
      {err && <p className="text-sm text-red-400">{err}</p>}
      {msg && <p className="text-sm text-emerald-400">{msg}</p>}
      {!row && !err && <p className="text-sm text-slate-400">Loading payment…</p>}
      {row && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${statusClass(row.status)}`}>
              {statusLabel(row.status)}
            </span>
            <div className="flex flex-wrap gap-2">
              {isPendingStatus(row.status) && (
                <>
                  <button
                    type="button"
                    className="rounded-lg bg-emerald-700 px-3 py-1.5 text-sm text-white hover:bg-emerald-600"
                    onClick={() => setVerifyOpen(true)}
                  >
                    Verify Payment
                  </button>
                  <button
                    type="button"
                    className="rounded-lg border border-red-700 px-3 py-1.5 text-sm text-red-200 hover:bg-red-950"
                    onClick={() => setRejectOpen(true)}
                  >
                    Reject Payment
                  </button>
                </>
              )}
              {row.status === "verified" && (
                <span className="text-sm text-slate-500">View Payment · invoice generation comes next</span>
              )}
              {row.status === "rejected" && <span className="text-sm text-slate-500">View Details</span>}
            </div>
          </div>

          <Section title="Customer details">
            <DetailRow label="Customer name" value={row.customer_name || "—"} />
            <DetailRow label="Company name" value={row.company_name || "—"} />
            <DetailRow label="Email" value={row.email || "—"} mono />
            <DetailRow label="Phone number" value={row.phone || "—"} />
            <DetailRow label="User ID" value={row.user_id != null ? String(row.user_id) : "—"} mono />
            <DetailRow label="Customer ID" value={row.customer_id != null ? String(row.customer_id) : "—"} mono />
            <DetailRow label="Billing address" value={row.billing_address || "—"} />
            <DetailRow label="City" value={row.city || "—"} />
            <DetailRow label="State" value={row.state || "—"} />
            <DetailRow label="State code" value={row.state_code || "—"} />
            <DetailRow label="Pincode" value={row.pincode || "—"} />
            <DetailRow label="GSTIN" value={row.gstin || "—"} />
          </Section>

          <Section title="Product / module">
            <DetailRow label="Module" value={row.module_label || "FIR"} />
            <DetailRow label="Plan" value={row.subscription_plan} />
            <DetailRow label="Plan type" value={row.plan_type || "—"} />
            <DetailRow label="Billing period" value={row.billing_period_label || row.billing_period || "—"} />
            <DetailRow label="Subscription duration" value={row.subscription_duration || "—"} />
            <DetailRow
              label="Subscription start date"
              value={formatDateOnly(row.subscription_start_date || row.subscription_start)}
            />
            <DetailRow
              label="Subscription end date"
              value={formatDateOnly(row.subscription_end_date || row.subscription_end)}
            />
          </Section>

          <Section title="Payment details">
            <DetailRow label="Payment ID" value={row.payment_code || String(row.id)} mono />
            <DetailRow label="Amount" value={`₹${row.amount_inr}`} />
            <DetailRow label="Currency" value={row.currency || "INR"} />
            <DetailRow label="Payment method" value={row.payment_method} />
            <DetailRow label="Payment reference / transaction ID" value={row.reference_note || "—"} mono />
            <DetailRow label="Payment date" value={formatWhen(row.payment_date)} />
            <DetailRow label="Payment submitted at" value={formatWhen(row.payment_submitted_at || row.payment_date)} />
            <DetailRow label="Payment verified at" value={formatWhen(row.payment_verified_at || row.verified_at)} />
            <DetailRow label="Current status" value={statusLabel(row.status)} />
            {row.rejection_reason_label ? <DetailRow label="Rejection reason" value={row.rejection_reason_label} /> : null}
          </Section>

          <Section title="Pricing snapshot">
            <DetailRow label="Plan" value={String(row.pricing_snapshot?.plan || row.subscription_plan)} />
            <DetailRow
              label="Billing period"
              value={String(row.pricing_snapshot?.billing_period_label || row.billing_period_label || "—")}
            />
            <DetailRow
              label="Original plan price"
              value={row.original_plan_price != null ? `₹${row.original_plan_price}` : "—"}
            />
            <DetailRow label="Amount submitted" value={`₹${row.amount_inr}`} />
          </Section>

          <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4 space-y-2">
            <h3 className="text-sm font-semibold text-white">Payment Screenshot Verification</h3>
            <p className="text-sm text-slate-300">Customer has reported payment as completed.</p>
            <p className="text-sm text-slate-400">
              Please verify the payment screenshot received on WhatsApp against the payment details below.
            </p>
            <p className="text-sm text-slate-300">
              {row.customer_name} · {row.module_label} · {row.subscription_plan} · {row.billing_period_label} · ₹
              {row.amount_inr} · {row.reference_note || "—"} · {formatWhen(row.payment_submitted_at || row.payment_date)}
            </p>
            {row.whatsapp_url ? (
              <a
                href={row.whatsapp_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-emerald-500"
              >
                Open WhatsApp
              </a>
            ) : (
              <p className="text-sm text-slate-400">WhatsApp: {row.whatsapp_number || "not configured"}</p>
            )}
          </div>

          {row.company_id ? (
            <Link className="text-sm text-brand-600 hover:underline" to={`/admin/companies/${row.company_id}`}>
              Open company
            </Link>
          ) : null}
        </div>
      )}

      {verifyOpen && row ? (
        <Modal onClose={() => !busy && setVerifyOpen(false)}>
          <h3 className="text-lg font-semibold text-white">Confirm payment verification</h3>
          <dl className="mt-4 space-y-1 text-sm text-slate-300">
            <p>Customer: {row.customer_name}</p>
            <p>Module: {row.module_label}</p>
            <p>Plan: {row.subscription_plan}</p>
            <p>Billing Period: {row.billing_period_label}</p>
            <p>Duration: {row.subscription_duration}</p>
            <p>Amount: ₹{row.amount_inr}</p>
            <p>Payment Method: {row.payment_method}</p>
            <p>Payment Reference: {row.reference_note || "—"}</p>
            <p>Payment Submitted: {formatWhen(row.payment_submitted_at || row.payment_date)}</p>
          </dl>
          <p className="mt-4 text-sm text-slate-400">
            Confirm that you have checked the payment in WhatsApp and verified that the payment has been received.
          </p>
          <p className="mt-2 text-xs text-slate-500">
            Subscription start and end dates will be set from the time you confirm. Invoice generation comes later.
          </p>
          <div className="mt-6 flex justify-end gap-2">
            <button
              type="button"
              className="rounded-lg border border-slate-600 px-4 py-2 text-sm text-slate-200"
              disabled={busy}
              onClick={() => setVerifyOpen(false)}
            >
              Cancel
            </button>
            <button
              type="button"
              className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
              disabled={busy}
              onClick={() => void confirmVerify()}
            >
              Confirm Payment Verification
            </button>
          </div>
        </Modal>
      ) : null}

      {rejectOpen && row ? (
        <Modal onClose={() => !busy && setRejectOpen(false)}>
          <h3 className="text-lg font-semibold text-white">Reject payment</h3>
          <label className="mt-4 block text-xs uppercase text-slate-500">
            Reason
            <select
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value as (typeof REJECT_REASONS)[number]["value"])}
            >
              {REJECT_REASONS.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </label>
          <label className="mt-3 block text-xs uppercase text-slate-500">
            Note {rejectReason === "other" ? "(required)" : "(optional)"}
            <textarea
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
              rows={3}
              value={rejectNote}
              onChange={(e) => setRejectNote(e.target.value)}
            />
          </label>
          <div className="mt-6 flex justify-end gap-2">
            <button
              type="button"
              className="rounded-lg border border-slate-600 px-4 py-2 text-sm text-slate-200"
              disabled={busy}
              onClick={() => setRejectOpen(false)}
            >
              Cancel
            </button>
            <button
              type="button"
              className="rounded-lg border border-red-700 bg-red-950 px-4 py-2 text-sm font-semibold text-red-100 disabled:opacity-50"
              disabled={busy}
              onClick={() => void confirmReject()}
            >
              Reject Payment
            </button>
          </div>
        </Modal>
      ) : null}
    </AdminBillingShell>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold text-white">{title}</h3>
      <div className="overflow-x-auto rounded-xl border border-slate-800">
        <table className="min-w-full text-left text-sm">
          <tbody className="divide-y divide-slate-800">{children}</tbody>
        </table>
      </div>
    </div>
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

function Modal({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="presentation"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}
