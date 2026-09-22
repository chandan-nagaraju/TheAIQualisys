import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../../api";

type CompanyProfile = {
  id: number;
  company_name: string;
  vendor_code: string;
  billing_address: string | null;
  billing_city: string | null;
  billing_state: string | null;
  billing_state_code: string | null;
  billing_pincode: string | null;
  gstin: string | null;
  phone: string | null;
};

type Me = {
  user: { email: string; name: string | null };
  company: CompanyProfile;
};

type FormState = {
  company_name: string;
  billing_address: string;
  billing_city: string;
  billing_state: string;
  billing_state_code: string;
  billing_pincode: string;
  gstin: string;
  phone: string;
};

function fromCompany(c: CompanyProfile): FormState {
  return {
    company_name: c.company_name || "",
    billing_address: c.billing_address || "",
    billing_city: c.billing_city || "",
    billing_state: c.billing_state || "",
    billing_state_code: c.billing_state_code || "",
    billing_pincode: c.billing_pincode || "",
    gstin: c.gstin || "",
    phone: c.phone || "",
  };
}

export default function ProfilePage() {
  const [form, setForm] = useState<FormState | null>(null);
  const [email, setEmail] = useState("");
  const [vendor, setVendor] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    apiFetch<Me>("/auth/me")
      .then((data) => {
        setEmail(data.user.email);
        setVendor(data.company.vendor_code);
        setForm(fromCompany(data.company));
      })
      .catch((e) => setErr(e instanceof Error ? e.message : "Failed to load profile"));
  }, []);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((f) => (f ? { ...f, [key]: value } : f));
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!form) return;
    setErr(null);
    setMsg(null);
    if (!form.company_name.trim()) {
      setErr("Company name is required.");
      return;
    }
    setSaving(true);
    try {
      const saved = await apiFetch<CompanyProfile>("/auth/company-profile", {
        method: "PUT",
        body: JSON.stringify({
          company_name: form.company_name.trim(),
          billing_address: form.billing_address.trim() || null,
          billing_city: form.billing_city.trim() || null,
          billing_state: form.billing_state.trim() || null,
          billing_state_code: form.billing_state_code.trim() || null,
          billing_pincode: form.billing_pincode.trim() || null,
          gstin: form.gstin.trim() || null,
          phone: form.phone.trim() || null,
        }),
      });
      setForm(fromCompany(saved));
      setMsg("Company and GST details saved. These values are used as the invoice buyer (Bill To).");
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
        <h1 className="text-xl font-semibold text-slate-900">Profile settings</h1>
        <p className="mt-2 text-sm text-slate-600">
          Manage your company billing details. This information appears as Bill To on subscription invoices.
        </p>
        {err && <p className="mt-3 text-sm text-red-600">{err}</p>}
        {msg && <p className="mt-3 text-sm text-green-700">{msg}</p>}
        {!form ? (
          !err ? <p className="mt-4 text-sm text-slate-500">Loading…</p> : null
        ) : (
          <form className="mt-6 max-w-2xl space-y-5" onSubmit={(e) => void save(e)}>
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Company details</h2>
              <p className="mt-1 text-xs text-slate-500">
                Vendor code {vendor || "—"} (assigned at signup). Account email {email || "—"}.
              </p>
            </div>
            <Field label="Company name" value={form.company_name} onChange={(v) => set("company_name", v)} required />
            <Field
              label="Business address"
              value={form.billing_address}
              onChange={(v) => set("billing_address", v)}
              area
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="City" value={form.billing_city} onChange={(v) => set("billing_city", v)} />
              <Field label="State" value={form.billing_state} onChange={(v) => set("billing_state", v)} />
              <Field label="State code" value={form.billing_state_code} onChange={(v) => set("billing_state_code", v)} />
              <Field label="Pincode" value={form.billing_pincode} onChange={(v) => set("billing_pincode", v)} />
              <Field label="Phone" value={form.phone} onChange={(v) => set("phone", v)} />
            </div>
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">GST details</h2>
              <p className="mt-1 text-xs text-slate-500">
                GSTIN and state code are used with TheAIQualisys seller details when generating invoices.
              </p>
            </div>
            <Field label="GSTIN" value={form.gstin} onChange={(v) => set("gstin", v)} />
            <button
              type="submit"
              disabled={saving}
              className="rounded bg-blue-700 px-4 py-2 text-sm font-medium text-white hover:bg-blue-800 disabled:opacity-60"
            >
              {saving ? "Saving…" : "Save company details"}
            </button>
          </form>
        )}
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6 sm:max-w-md">
        <h2 className="text-sm font-semibold text-slate-900">Account</h2>
        <Link
          to="/profile/change-password"
          className="mt-3 inline-flex min-h-11 w-full items-center justify-center rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50"
        >
          Change password
        </Link>
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  area,
  required,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  area?: boolean;
  required?: boolean;
}) {
  return (
    <label className="block text-xs font-medium text-slate-600">
      {label}
      {required ? <span className="text-red-600"> *</span> : null}
      {area ? (
        <textarea
          className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm text-slate-900"
          rows={3}
          value={value}
          required={required}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <input
          className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm text-slate-900"
          value={value}
          required={required}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </label>
  );
}
