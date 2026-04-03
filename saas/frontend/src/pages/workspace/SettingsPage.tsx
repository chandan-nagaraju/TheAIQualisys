import { FormEvent, useEffect, useState } from "react";
import { workspaceFetch } from "../../api";

type St = {
  company_name: string;
  format_no: string;
  issue_date: string;
  doc_rev_no: string;
  rev_date: string;
  logo_url: string | null;
  inspector_signature_url: string | null;
  quality_signature_url: string | null;
};

export default function SettingsPage() {
  const [s, setS] = useState<St | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    workspaceFetch<St>("/api/app/settings")
      .then(setS)
      .catch((e) => setErr(e.message));
  }, []);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const API_BASE = import.meta.env.VITE_API_URL ?? "";
    const t = localStorage.getItem("fir_token");
    const cid = localStorage.getItem("fir_workspace_customer_id");
    const h: Record<string, string> = {};
    if (t) h.Authorization = `Bearer ${t}`;
    if (cid) h["X-Customer-Id"] = cid;
    const res = await fetch(`${API_BASE}/api/app/settings`, { method: "POST", headers: h, body: fd });
    if (!res.ok) {
      setErr(await res.text());
      return;
    }
    setS(await res.json());
    setErr(null);
  }

  if (err && !s) {
    return <p className="text-red-600">{err}</p>;
  }
  if (!s) {
    return <p>Loading…</p>;
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h1 className="text-xl font-semibold">Global FIR settings</h1>
      {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
      <form onSubmit={onSubmit} className="mt-6 max-w-lg space-y-4">
        <div>
          <label className="text-xs text-slate-500">Company name</label>
          <input name="company_name" className="mt-1 w-full rounded border px-2 py-1 text-sm" defaultValue={s.company_name} />
        </div>
        <div>
          <label className="text-xs text-slate-500">Format no</label>
          <input name="format_no" className="mt-1 w-full rounded border px-2 py-1 text-sm" defaultValue={s.format_no} />
        </div>
        <div>
          <label className="text-xs text-slate-500">Issue date</label>
          <input name="issue_date" className="mt-1 w-full rounded border px-2 py-1 text-sm" defaultValue={s.issue_date} />
        </div>
        <div>
          <label className="text-xs text-slate-500">Doc rev no</label>
          <input name="doc_rev_no" className="mt-1 w-full rounded border px-2 py-1 text-sm" defaultValue={s.doc_rev_no} />
        </div>
        <div>
          <label className="text-xs text-slate-500">Rev date</label>
          <input name="rev_date" className="mt-1 w-full rounded border px-2 py-1 text-sm" defaultValue={s.rev_date} />
        </div>
        <div>
          <label className="text-xs text-slate-500">Logo</label>
          <input name="logo" type="file" accept="image/*" className="mt-1 block text-sm" />
          {s.logo_url && (
            <img src={s.logo_url} alt="Logo" className="mt-2 h-16 object-contain" />
          )}
        </div>
        <div>
          <label className="text-xs text-slate-500">Inspector signature</label>
          <input name="inspector_signature" type="file" accept="image/*" className="mt-1 block text-sm" />
        </div>
        <div>
          <label className="text-xs text-slate-500">Quality signature</label>
          <input name="quality_signature" type="file" accept="image/*" className="mt-1 block text-sm" />
        </div>
        <button type="submit" className="rounded bg-blue-700 px-4 py-2 text-sm text-white">
          Save settings
        </button>
      </form>
    </div>
  );
}
