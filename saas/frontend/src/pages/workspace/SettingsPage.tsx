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
  const [okMsg, setOkMsg] = useState<string | null>(null);

  useEffect(() => {
    workspaceFetch<St>("/api/app/settings")
      .then(setS)
      .catch((e) => setErr(e.message));
  }, []);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    try {
      const saved = await workspaceFetch<St>("/api/app/settings", { method: "POST", body: fd });
      setS(saved);
      setErr(null);
      setOkMsg("Settings saved. Uploaded images are now shared for all users/devices.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to save settings");
      setOkMsg(null);
    }
  }

  if (err && !s) {
    return <p className="text-red-600">{err}</p>;
  }
  if (!s) {
    return <p>Loading…</p>;
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
      <h1 className="text-xl font-semibold">Global FIR settings</h1>
      <p className="mt-2 text-sm text-slate-600">
        This page now stores logo/signatures in shared backend storage so they are visible across all machines.
      </p>
      {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
      {okMsg && <p className="mt-2 text-sm text-green-700">{okMsg}</p>}
      <form onSubmit={onSubmit} className="mt-6 grid gap-5 lg:grid-cols-3 lg:gap-6">
        <div className="space-y-4 lg:col-span-2">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className="text-xs text-slate-500">Company name</label>
              <input
                name="company_name"
                className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm"
                defaultValue={s.company_name}
              />
            </div>
            <div>
              <label className="text-xs text-slate-500">Format no</label>
              <input
                name="format_no"
                className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm"
                defaultValue={s.format_no}
              />
            </div>
            <div>
              <label className="text-xs text-slate-500">Doc rev no</label>
              <input
                name="doc_rev_no"
                className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm"
                defaultValue={s.doc_rev_no}
              />
            </div>
            <div>
              <label className="text-xs text-slate-500">Issue date</label>
              <input
                name="issue_date"
                className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm"
                defaultValue={s.issue_date}
              />
            </div>
            <div>
              <label className="text-xs text-slate-500">Rev date</label>
              <input
                name="rev_date"
                className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm"
                defaultValue={s.rev_date}
              />
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <label className="text-xs font-medium text-slate-600">Logo</label>
              <input name="logo" type="file" accept="image/*" className="mt-2 block w-full text-sm" />
              {s.logo_url && <img src={s.logo_url} alt="Logo" className="mt-3 h-20 w-full rounded bg-white object-contain p-1" />}
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <label className="text-xs font-medium text-slate-600">Inspector signature</label>
              <input name="inspector_signature" type="file" accept="image/*" className="mt-2 block w-full text-sm" />
              {s.inspector_signature_url && (
                <img src={s.inspector_signature_url} alt="Inspector signature" className="mt-3 h-20 w-full rounded bg-white object-contain p-1" />
              )}
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <label className="text-xs font-medium text-slate-600">Quality signature</label>
              <input name="quality_signature" type="file" accept="image/*" className="mt-2 block w-full text-sm" />
              {s.quality_signature_url && (
                <img src={s.quality_signature_url} alt="Quality signature" className="mt-3 h-20 w-full rounded bg-white object-contain p-1" />
              )}
            </div>
          </div>
        </div>

        <div className="lg:col-span-1">
          <div className="sticky top-4 rounded-lg border border-slate-200 bg-slate-50 p-4">
            <h2 className="text-sm font-semibold text-slate-800">Tips</h2>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-slate-600">
              <li>Use PNG/JPG images with transparent or white background.</li>
              <li>Click Save settings after selecting files.</li>
              <li>Images are shared for all users of your company.</li>
            </ul>
            <button type="submit" className="mt-4 w-full rounded bg-blue-700 px-4 py-2.5 text-sm font-medium text-white">
              Save settings
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
