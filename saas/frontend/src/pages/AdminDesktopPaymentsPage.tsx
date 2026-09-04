import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiFetch } from "../api";

type Order = {
  id: number;
  order_number: string;
  product_name: string;
  plan_name: string;
  seats: number;
  total_price_inr: number;
  status: string;
  user_id: number;
  company_id: number;
};

type PaymentRequest = {
  id: number;
  order_id: number;
  amount_inr: number;
  reference_note: string | null;
  has_screenshot: boolean;
  status: string;
  review_note: string | null;
  order: Order | null;
};

type UpiSettings = {
  upi_id: string;
  payee_name: string;
  instructions: string | null;
  has_qr_image: boolean;
};

export default function AdminDesktopPaymentsPage() {
  const nav = useNavigate();
  const [rows, setRows] = useState<PaymentRequest[]>([]);
  const [upi, setUpi] = useState<UpiSettings | null>(null);
  const [upiId, setUpiId] = useState("");
  const [payee, setPayee] = useState("");
  const [instructions, setInstructions] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [disabled, setDisabled] = useState(false);
  const [tick, setTick] = useState(0);
  const [rejectReasons, setRejectReasons] = useState<Record<number, string>>({});
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!localStorage.getItem("fir_admin_token")) {
      nav("/login");
      return;
    }
    let cancelled = false;
    (async () => {
      setErr(null);
      setDisabled(false);
      try {
        const [reqs, settings] = await Promise.all([
          apiFetch<PaymentRequest[]>("/api/admin/desktop/payment-requests?status=pending_review", {
            token: "admin",
          }),
          apiFetch<UpiSettings>("/api/admin/desktop/upi-settings", { token: "admin" }),
        ]);
        if (cancelled) return;
        setRows(reqs);
        setUpi(settings);
        setUpiId(settings.upi_id);
        setPayee(settings.payee_name);
        setInstructions(settings.instructions || "");
      } catch (e) {
        const m = e instanceof Error ? e.message : "Failed";
        if (/404|Not found/i.test(m)) setDisabled(true);
        else setErr(m);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [nav, tick]);

  async function saveUpi(e: FormEvent) {
    e.preventDefault();
    setMsg(null);
    try {
      await apiFetch("/api/admin/desktop/upi-settings", {
        method: "PUT",
        token: "admin",
        body: JSON.stringify({
          upi_id: upiId,
          payee_name: payee,
          instructions,
        }),
      });
      setMsg("UPI settings saved.");
      setTick((x) => x + 1);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Save failed");
    }
  }

  async function approve(id: number) {
    setMsg(null);
    try {
      const res = await apiFetch<{ licenses_minted: number }>(
        `/api/admin/desktop/payment-requests/${id}/approve`,
        { method: "POST", token: "admin", body: "{}" },
      );
      setMsg(`Approved. Minted ${res.licenses_minted} independent license(s).`);
      setTick((x) => x + 1);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Approve failed");
    }
  }

  async function reject(id: number) {
    setMsg(null);
    const reason = (rejectReasons[id] || "").trim();
    if (reason.length < 3) {
      setErr("Rejection reason is required");
      return;
    }
    try {
      await apiFetch(`/api/admin/desktop/payment-requests/${id}/reject`, {
        method: "POST",
        token: "admin",
        body: JSON.stringify({ reason }),
      });
      setMsg("Payment rejected.");
      setTick((x) => x + 1);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Reject failed");
    }
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-white">Desktop payment requests</h1>
        <Link to="/admin" className="text-sm text-brand-500 hover:underline">
          ← Admin home
        </Link>
      </div>

      {disabled && (
        <p className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-4 py-3 text-sm text-amber-100">
          Desktop licensing is disabled (<code>ENABLE_DESKTOP_LICENSING</code>).
        </p>
      )}
      {err && <p className="text-sm text-red-400">{err}</p>}
      {msg && <p className="text-sm text-emerald-400">{msg}</p>}

      {!disabled && (
        <form onSubmit={saveUpi} className="rounded-xl border border-slate-800 bg-slate-900/50 p-4 space-y-3 max-w-xl">
          <h2 className="text-sm font-semibold text-slate-200">UPI configuration</h2>
          <label className="block text-xs text-slate-500">
            UPI ID
            <input
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
              value={upiId}
              onChange={(e) => setUpiId(e.target.value)}
              required
            />
          </label>
          <label className="block text-xs text-slate-500">
            Payee name
            <input
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
              value={payee}
              onChange={(e) => setPayee(e.target.value)}
              required
            />
          </label>
          <label className="block text-xs text-slate-500">
            Instructions
            <textarea
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
              rows={3}
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
            />
          </label>
          <button type="submit" className="rounded bg-brand-600 px-3 py-1.5 text-xs text-white">
            Save UPI settings
          </button>
          {upi && (
            <p className="text-xs text-slate-500">
              Current: {upi.payee_name} · {upi.upi_id || "(empty)"}
            </p>
          )}
        </form>
      )}

      <section className="space-y-4">
        <h2 className="text-lg font-semibold text-white">Pending review</h2>
        {rows.length === 0 && !disabled && (
          <p className="text-sm text-slate-400">No payment requests awaiting review.</p>
        )}
        {rows.map((r) => (
          <div key={r.id} className="rounded-xl border border-slate-800 bg-slate-900/50 p-4 space-y-3">
            <div className="flex flex-wrap justify-between gap-2">
              <div>
                <p className="font-mono text-sm text-brand-400">{r.order?.order_number || `order #${r.order_id}`}</p>
                <p className="text-sm text-white">
                  {r.order?.product_name} · {r.order?.plan_name} · {r.order?.seats} seat(s)
                </p>
                <p className="text-xs text-slate-400">
                  Amount ₹{r.amount_inr} · UTR {r.reference_note || "—"}
                  {r.has_screenshot ? " · screenshot attached" : ""}
                </p>
              </div>
              <p className="text-xs text-amber-300">{r.status}</p>
            </div>
            <div className="flex flex-wrap gap-2 items-end">
              <button
                type="button"
                onClick={() => approve(r.id)}
                className="rounded bg-emerald-700 px-3 py-1.5 text-xs text-white hover:bg-emerald-600"
              >
                Approve &amp; mint {r.order?.seats ?? "?"} license(s)
              </button>
              <label className="block text-xs text-slate-500 flex-1 min-w-[12rem]">
                Reject reason
                <input
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
                  value={rejectReasons[r.id] || ""}
                  onChange={(e) => setRejectReasons((m) => ({ ...m, [r.id]: e.target.value }))}
                  placeholder="Required"
                />
              </label>
              <button
                type="button"
                onClick={() => reject(r.id)}
                className="rounded border border-red-700 px-3 py-1.5 text-xs text-red-200 hover:bg-red-950"
              >
                Reject
              </button>
            </div>
          </div>
        ))}
      </section>
    </div>
  );
}
