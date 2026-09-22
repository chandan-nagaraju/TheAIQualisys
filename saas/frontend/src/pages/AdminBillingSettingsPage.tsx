import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiFetch } from "../api";
import AdminBillingShell from "../components/AdminBillingShell";

type Settings = {
  business_name: string | null;
  business_address: string | null;
  gstin: string | null;
  state: string | null;
  state_code: string | null;
  email: string | null;
  phone: string | null;
  logo_path: string | null;
  invoice_prefix: string | null;
  cgst_rate: number | null;
  sgst_rate: number | null;
  igst_rate: number | null;
  terms_notes: string | null;
};

const EMPTY: Settings = {
  business_name: "",
  business_address: "",
  gstin: "",
  state: "",
  state_code: "",
  email: "",
  phone: "",
  logo_path: "",
  invoice_prefix: "INV-",
  cgst_rate: 9,
  sgst_rate: 9,
  igst_rate: 18,
  terms_notes: "",
};

export default function AdminBillingSettingsPage() {
  const nav = useNavigate();
  const [form, setForm] = useState<Settings>(EMPTY);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!localStorage.getItem("fir_admin_token")) {
      nav("/login");
      return;
    }
    apiFetch<Settings>("/admin/billing/settings", { token: "admin" })
      .then((s) => setForm({ ...EMPTY, ...s }))
      .catch((e) => setErr(e instanceof Error ? e.message : "Failed to load settings"));
  }, [nav]);

  function set<K extends keyof Settings>(key: K, value: Settings[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    try {
      const saved = await apiFetch<Settings>("/admin/billing/settings", {
        method: "PUT",
        token: "admin",
        body: JSON.stringify(form),
      });
      setForm({ ...EMPTY, ...saved });
      setMsg("Billing settings saved. These values are used as the invoice seller and GST rates.");
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Save failed");
    }
  }

  return (
    <AdminBillingShell
      title="Billing settings"
      description="Seller (TheAIQualisys) details and GST rates used when generating subscription invoices. Customer GST/state is stored on the company record."
    >
      {err && <p className="text-sm text-red-400">{err}</p>}
      {msg && <p className="text-sm text-emerald-400">{msg}</p>}
      <form className="max-w-xl space-y-3" onSubmit={(e) => void save(e)}>
        <Field label="Business name" value={form.business_name || ""} onChange={(v) => set("business_name", v)} />
        <Field label="Business address" value={form.business_address || ""} onChange={(v) => set("business_address", v)} area />
        <Field label="GSTIN" value={form.gstin || ""} onChange={(v) => set("gstin", v)} />
        <Field label="State" value={form.state || ""} onChange={(v) => set("state", v)} />
        <Field label="State code" value={form.state_code || ""} onChange={(v) => set("state_code", v)} />
        <Field label="Email" value={form.email || ""} onChange={(v) => set("email", v)} />
        <Field label="Phone" value={form.phone || ""} onChange={(v) => set("phone", v)} />
        <Field label="Logo path / URL" value={form.logo_path || ""} onChange={(v) => set("logo_path", v)} />
        <Field label="Invoice prefix" value={form.invoice_prefix || "INV-"} onChange={(v) => set("invoice_prefix", v)} />
        <Field label="CGST rate %" value={String(form.cgst_rate ?? 9)} onChange={(v) => set("cgst_rate", Number(v))} />
        <Field label="SGST rate %" value={String(form.sgst_rate ?? 9)} onChange={(v) => set("sgst_rate", Number(v))} />
        <Field label="IGST rate %" value={String(form.igst_rate ?? 18)} onChange={(v) => set("igst_rate", Number(v))} />
        <Field label="Terms / notes" value={form.terms_notes || ""} onChange={(v) => set("terms_notes", v)} area />
        <button type="submit" className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white">
          Save settings
        </button>
      </form>
    </AdminBillingShell>
  );
}

function Field({
  label,
  value,
  onChange,
  area,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  area?: boolean;
}) {
  return (
    <label className="block text-xs uppercase text-slate-500">
      {label}
      {area ? (
        <textarea
          className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm normal-case text-white"
          rows={3}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <input
          className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm normal-case text-white"
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </label>
  );
}
