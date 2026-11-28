import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiFetch } from "../api";

type LicenseRow = {
  id: number;
  licensed_user_id: number;
  company_id: number;
  product_name?: string | null;
  plan_name?: string | null;
  order_number?: string | null;
  order_id?: number | null;
  seat_index?: number | null;
  entitlement_type?: string;
  status: string;
  key_masked: string;
  key_prefix: string;
  key_last4: string;
  device_status: string;
  issued_at?: string | null;
  expires_at?: string | null;
};

/** Admin: masked license metadata + resend email. Explicit reveal is audited server-side. */
export default function AdminDesktopLicensesPage() {
  const nav = useNavigate();
  const [rows, setRows] = useState<LicenseRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [disabled, setDisabled] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setErr(null);
    setDisabled(false);
    try {
      const data = await apiFetch<LicenseRow[]>("/api/admin/desktop/licenses", { token: "admin" });
      setRows(data);
    } catch (e) {
      const m = e instanceof Error ? e.message : "Failed";
      if (/404|Not found/i.test(m)) setDisabled(true);
      else setErr(m);
    }
  };

  useEffect(() => {
    if (!localStorage.getItem("fir_admin_token")) {
      nav("/login");
      return;
    }
    void load();
  }, [nav]);

  const resend = async (orderId: number) => {
    setBusy(true);
    setMsg(null);
    setErr(null);
    try {
      await apiFetch(`/api/admin/desktop/orders/${orderId}/resend-license-email`, {
        method: "POST",
        body: "{}",
        token: "admin",
      });
      setMsg(`Resent license email for order ${orderId}.`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Resend failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-white">Desktop licenses</h1>
        <div className="flex flex-wrap gap-4 text-sm">
          <Link to="/admin/desktop-payments" className="text-brand-500 hover:underline">
            Payments
          </Link>
          <Link to="/admin" className="text-brand-500 hover:underline">
            ← Admin
          </Link>
        </div>
      </div>
      <p className="text-sm text-slate-400">
        Masked keys only. Full keys are not listed here — use explicit reveal API if support requires it (audited).
      </p>
      {disabled && (
        <p className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-4 py-3 text-sm text-amber-100">
          Desktop licensing is not enabled on this environment yet.
        </p>
      )}
      {err && <p className="text-sm text-red-400">{err}</p>}
      {msg && <p className="text-sm text-emerald-400">{msg}</p>}
      <div className="space-y-3">
        {rows.map((lic) => (
          <div key={lic.id} className="rounded-xl border border-slate-800 bg-slate-900/50 p-4 text-sm">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="text-white">
                {lic.product_name || `Product #${lic.id}`} ·{" "}
                {(lic.entitlement_type || "paid").toLowerCase() === "trial"
                  ? "Trial"
                  : lic.plan_name || "Plan"}{" "}
                · Seat {lic.seat_index ?? "—"}
              </span>
              <span className="text-xs text-slate-400">
                {(lic.entitlement_type || "paid").toLowerCase()} · {lic.status} / {lic.device_status}
              </span>
            </div>
            <p className="mt-1 font-mono text-xs text-slate-400">{lic.key_masked}</p>
            <p className="mt-1 text-xs text-slate-500">
              User #{lic.licensed_user_id} · Company #{lic.company_id}
              {lic.order_number ? ` · ${lic.order_number}` : ""}
              {" · "}
              Expires {lic.expires_at ? new Date(lic.expires_at).toLocaleDateString() : "—"}
            </p>
            {lic.order_id != null && (
              <button
                type="button"
                disabled={busy}
                onClick={() => void resend(lic.order_id!)}
                className="mt-2 text-xs text-brand-400 hover:underline disabled:opacity-40"
              >
                Resend license email
              </button>
            )}
          </div>
        ))}
      </div>
      {!disabled && !err && rows.length === 0 && (
        <p className="text-sm text-slate-400">No licenses minted yet.</p>
      )}
    </div>
  );
}
