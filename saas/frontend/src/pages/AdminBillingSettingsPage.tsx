import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiFetch } from "../api";
import AdminBillingShell from "../components/AdminBillingShell";

type Settings = {
  business_name: string | null;
  legal_business_name: string | null;
  business_address: string | null;
  address_line1: string | null;
  address_line2: string | null;
  city: string | null;
  state: string | null;
  state_code: string | null;
  pincode: string | null;
  country: string | null;
  email: string | null;
  phone: string | null;
  website: string | null;
  gstin: string | null;
  pan: string | null;
};

const EMPTY: Settings = {
  business_name: "",
  legal_business_name: "",
  business_address: "",
  address_line1: "",
  address_line2: "",
  city: "",
  state: "",
  state_code: "",
  pincode: "",
  country: "India",
  email: "",
  phone: "",
  website: "",
  gstin: "",
  pan: "",
};

const SETTINGS_PATH = "/admin/billing/settings";

function asForm(s: Partial<Settings> | null | undefined): Settings {
  return {
    ...EMPTY,
    ...Object.fromEntries(Object.entries(s || {}).map(([k, v]) => [k, v ?? ""])),
    country: (s?.country || "India") as string,
  };
}

export default function AdminBillingSettingsPage() {
  const nav = useNavigate();
  const [form, setForm] = useState<Settings>(EMPTY);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!localStorage.getItem("fir_admin_token")) {
      nav("/login");
      return;
    }
    setLoading(true);
    apiFetch<Settings>(SETTINGS_PATH, { token: "admin" })
      .then((s) => {
        setForm(asForm(s));
        setErr(null);
      })
      .catch((e) => setErr(e instanceof Error ? e.message : "Failed to load settings"))
      .finally(() => setLoading(false));
  }, [nav]);

  function set<K extends keyof Settings>(key: K, value: Settings[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function validate(): string | null {
    const required: { key: keyof Settings; label: string }[] = [
      { key: "business_name", label: "Business Name" },
      { key: "address_line1", label: "Address Line 1" },
      { key: "city", label: "City" },
      { key: "state", label: "State" },
      { key: "state_code", label: "State Code" },
      { key: "pincode", label: "Pincode" },
      { key: "email", label: "Email" },
      { key: "phone", label: "Phone" },
      { key: "gstin", label: "GSTIN" },
    ];
    const missing = required.filter(({ key }) => !(form[key] || "").toString().trim());
    if (missing.length) {
      return `Please fill: ${missing.map((m) => m.label).join(", ")}.`;
    }
    return null;
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    const problem = validate();
    if (problem) {
      setErr(problem);
      return;
    }
    setSaving(true);
    try {
      const payload = {
        business_name: form.business_name,
        legal_business_name: form.legal_business_name,
        address_line1: form.address_line1,
        address_line2: form.address_line2,
        city: form.city,
        state: form.state,
        state_code: form.state_code,
        pincode: form.pincode,
        country: form.country || "India",
        email: form.email,
        phone: form.phone,
        website: form.website,
        gstin: form.gstin,
        pan: form.pan,
        business_address: [form.address_line1, form.address_line2].filter((x) => (x || "").trim()).join(", "),
      };
      const saved = await apiFetch<Settings>(SETTINGS_PATH, {
        method: "PUT",
        token: "admin",
        body: JSON.stringify(payload),
      });
      setForm(asForm(saved));
      setMsg("Billing settings saved. Seller details will be used on subscription invoices.");
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <AdminBillingShell
      title="Billing Settings"
      description="Manage TheAIQualisys seller details used when generating subscription invoices. Customer (buyer) details come from the company profile."
    >
      {err && <p className="text-sm text-red-400">{err}</p>}
      {msg && <p className="text-sm text-emerald-400">{msg}</p>}
      {loading ? (
        <p className="text-sm text-slate-400">Loading seller details…</p>
      ) : (
        <form className="max-w-3xl space-y-6" onSubmit={(e) => void save(e)}>
          <section className="rounded-xl border border-slate-800 bg-slate-900/50 p-4 space-y-3">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-300">Seller details</h3>
            <Field label="Business Name" value={form.business_name || ""} onChange={(v) => set("business_name", v)} required />
            <Field
              label="Legal Business Name"
              value={form.legal_business_name || ""}
              onChange={(v) => set("legal_business_name", v)}
            />
            <Field label="Address Line 1" value={form.address_line1 || ""} onChange={(v) => set("address_line1", v)} required />
            <Field label="Address Line 2" value={form.address_line2 || ""} onChange={(v) => set("address_line2", v)} />
            <div className="grid gap-3 md:grid-cols-2">
              <Field label="City" value={form.city || ""} onChange={(v) => set("city", v)} required />
              <Field label="State" value={form.state || ""} onChange={(v) => set("state", v)} required />
              <Field label="State Code" value={form.state_code || ""} onChange={(v) => set("state_code", v)} required />
              <Field label="Pincode" value={form.pincode || ""} onChange={(v) => set("pincode", v)} required />
              <Field label="Country" value={form.country || ""} onChange={(v) => set("country", v)} />
            </div>
          </section>

          <section className="rounded-xl border border-slate-800 bg-slate-900/50 p-4 space-y-3">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-300">Contact details</h3>
            <div className="grid gap-3 md:grid-cols-2">
              <Field label="Email" value={form.email || ""} onChange={(v) => set("email", v)} type="email" required />
              <Field label="Phone" value={form.phone || ""} onChange={(v) => set("phone", v)} required />
              <Field label="Website" value={form.website || ""} onChange={(v) => set("website", v)} />
            </div>
          </section>

          <section className="rounded-xl border border-slate-800 bg-slate-900/50 p-4 space-y-3">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-300">Tax details</h3>
            <p className="text-xs text-slate-500">
              Seller GSTIN and state are combined with the customer company profile when generating an invoice.
            </p>
            <div className="grid gap-3 md:grid-cols-2">
              <Field label="GSTIN" value={form.gstin || ""} onChange={(v) => set("gstin", v)} required />
              <Field label="PAN" value={form.pan || ""} onChange={(v) => set("pan", v)} />
            </div>
          </section>

          <button
            type="submit"
            disabled={saving}
            className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save Billing Settings"}
          </button>
        </form>
      )}
    </AdminBillingShell>
  );
}

function Field({
  label,
  value,
  onChange,
  area,
  type,
  required,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  area?: boolean;
  type?: string;
  required?: boolean;
}) {
  return (
    <label className="block text-xs uppercase text-slate-500">
      {label}
      {required ? <span className="text-red-400"> *</span> : null}
      {area ? (
        <textarea
          className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm normal-case text-white"
          rows={3}
          value={value}
          required={required}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <input
          className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm normal-case text-white"
          type={type || "text"}
          value={value}
          required={required}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </label>
  );
}
