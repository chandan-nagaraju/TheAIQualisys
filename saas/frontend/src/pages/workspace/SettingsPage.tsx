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
  char_critical_url: string | null;
  char_safety_url: string | null;
  char_important_url: string | null;
  quali_font_configured: boolean;
  s3_assets_enabled?: boolean;
};

type PresignResponse = {
  upload_url: string;
  storage_key: string;
  public_url: string;
  headers: Record<string, string>;
};

type AssetKind =
  | "logo"
  | "inspector_signature"
  | "quality_signature"
  | "char_critical"
  | "char_safety"
  | "char_important"
  | "quali_font";

type PendingS3 = Partial<Record<AssetKind, { key: string; url: string }>>;

const MAX_FONT_BYTES = 5 * 1024 * 1024;

async function presignAndPutToS3(kind: AssetKind, file: File): Promise<PresignResponse> {
  const contentType =
    file.type ||
    (kind === "quali_font" ? "application/octet-stream" : "image/png");
  const presign = await workspaceFetch<PresignResponse>("/api/app/settings/asset-upload-url", {
    method: "POST",
    body: JSON.stringify({ kind, content_type: contentType }),
  });
  const put = await fetch(presign.upload_url, {
    method: "PUT",
    body: file,
    headers: presign.headers,
  });
  if (!put.ok) {
    const t = await put.text().catch(() => "");
    throw new Error(t || `Upload to storage failed (${put.status})`);
  }
  return presign;
}

export default function SettingsPage() {
  const [s, setS] = useState<St | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);
  const [clearQualiFont, setClearQualiFont] = useState(false);
  const [pendingS3, setPendingS3] = useState<PendingS3>({});
  const [uploadBusy, setUploadBusy] = useState<AssetKind | null>(null);

  useEffect(() => {
    workspaceFetch<St>("/api/app/settings")
      .then((data) => {
        setS(data);
        setPendingS3({});
      })
      .catch((e) => setErr(e.message));
  }, []);

  async function onAssetFile(kind: AssetKind, file: File | undefined) {
    if (!file || !s?.s3_assets_enabled) return;
    if (kind === "quali_font" && file.size > MAX_FONT_BYTES) {
      setErr(`Font file too large (max ${MAX_FONT_BYTES / (1024 * 1024)} MB).`);
      return;
    }
    setErr(null);
    setUploadBusy(kind);
    try {
      const presign = await presignAndPutToS3(kind, file);
      setPendingS3((prev) => ({ ...prev, [kind]: { key: presign.storage_key, url: presign.public_url } }));
      if (kind === "quali_font") {
        setClearQualiFont(false);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploadBusy(null);
    }
  }

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    fd.set("clear_quali_font", clearQualiFont ? "1" : "");
    const s3On = !!s?.s3_assets_enabled;
    if (s3On) {
      if (pendingS3.logo) fd.set("logo_storage_key", pendingS3.logo.key);
      if (pendingS3.inspector_signature) fd.set("inspector_signature_storage_key", pendingS3.inspector_signature.key);
      if (pendingS3.quality_signature) fd.set("quality_signature_storage_key", pendingS3.quality_signature.key);
      if (pendingS3.char_critical) fd.set("char_critical_storage_key", pendingS3.char_critical.key);
      if (pendingS3.char_safety) fd.set("char_safety_storage_key", pendingS3.char_safety.key);
      if (pendingS3.char_important) fd.set("char_important_storage_key", pendingS3.char_important.key);
      if (pendingS3.quali_font) fd.set("quali_font_storage_key", pendingS3.quali_font.key);
    }
    try {
      const saved = await workspaceFetch<St>("/api/app/settings", { method: "POST", body: fd });
      setS(saved);
      setPendingS3({});
      setClearQualiFont(false);
      setErr(null);
      setOkMsg(
        s3On
          ? "Settings saved. Files are stored in your S3 bucket and linked from shared settings."
          : "Settings saved. Uploaded images are now shared for all users/devices.",
      );
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

  const s3On = !!s.s3_assets_enabled;
  const logoSrc = pendingS3.logo?.url ?? s.logo_url;
  const insSrc = pendingS3.inspector_signature?.url ?? s.inspector_signature_url;
  const qualSrc = pendingS3.quality_signature?.url ?? s.quality_signature_url;
  const critSrc = pendingS3.char_critical?.url ?? s.char_critical_url;
  const safetySrc = pendingS3.char_safety?.url ?? s.char_safety_url;
  const importantSrc = pendingS3.char_important?.url ?? s.char_important_url;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
      <h1 className="text-xl font-semibold">Global FIR settings</h1>
      <p className="mt-2 text-sm text-slate-600">
        {s3On
          ? "Logo, signatures, special-character legend images, and custom font upload directly to your S3 bucket. Only keys are stored in the database to reduce data transfer."
          : "This page stores logo, signatures, and special-character images in shared backend storage so they are visible across all machines."}
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
              <input
                {...(s3On ? {} : { name: "logo" })}
                type="file"
                accept="image/*"
                disabled={!!uploadBusy}
                className="mt-2 block w-full text-sm"
                onChange={(e) => void onAssetFile("logo", e.target.files?.[0])}
              />
              {uploadBusy === "logo" && <p className="mt-2 text-xs text-slate-500">Uploading…</p>}
              {logoSrc && <img src={logoSrc} alt="Logo" className="mt-3 h-20 w-full rounded bg-white object-contain p-1" />}
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <label className="text-xs font-medium text-slate-600">Inspector signature</label>
              <input
                {...(s3On ? {} : { name: "inspector_signature" })}
                type="file"
                accept="image/*"
                disabled={!!uploadBusy}
                className="mt-2 block w-full text-sm"
                onChange={(e) => void onAssetFile("inspector_signature", e.target.files?.[0])}
              />
              {uploadBusy === "inspector_signature" && <p className="mt-2 text-xs text-slate-500">Uploading…</p>}
              {insSrc && (
                <img src={insSrc} alt="Inspector signature" className="mt-3 h-20 w-full rounded bg-white object-contain p-1" />
              )}
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <label className="text-xs font-medium text-slate-600">Quality signature</label>
              <input
                {...(s3On ? {} : { name: "quality_signature" })}
                type="file"
                accept="image/*"
                disabled={!!uploadBusy}
                className="mt-2 block w-full text-sm"
                onChange={(e) => void onAssetFile("quality_signature", e.target.files?.[0])}
              />
              {uploadBusy === "quality_signature" && <p className="mt-2 text-xs text-slate-500">Uploading…</p>}
              {qualSrc && (
                <img src={qualSrc} alt="Quality signature" className="mt-3 h-20 w-full rounded bg-white object-contain p-1" />
              )}
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <label className="text-xs font-medium text-slate-600">Critical (special characteristic)</label>
              <input
                {...(s3On ? {} : { name: "char_critical" })}
                type="file"
                accept="image/*"
                disabled={!!uploadBusy}
                className="mt-2 block w-full text-sm"
                onChange={(e) => void onAssetFile("char_critical", e.target.files?.[0])}
              />
              {uploadBusy === "char_critical" && <p className="mt-2 text-xs text-slate-500">Uploading…</p>}
              {critSrc && (
                <img src={critSrc} alt="Critical characteristic" className="mt-3 h-20 w-full rounded bg-white object-contain p-1" />
              )}
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <label className="text-xs font-medium text-slate-600">Safety (special characteristic)</label>
              <input
                {...(s3On ? {} : { name: "char_safety" })}
                type="file"
                accept="image/*"
                disabled={!!uploadBusy}
                className="mt-2 block w-full text-sm"
                onChange={(e) => void onAssetFile("char_safety", e.target.files?.[0])}
              />
              {uploadBusy === "char_safety" && <p className="mt-2 text-xs text-slate-500">Uploading…</p>}
              {safetySrc && (
                <img src={safetySrc} alt="Safety characteristic" className="mt-3 h-20 w-full rounded bg-white object-contain p-1" />
              )}
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <label className="text-xs font-medium text-slate-600">Important (special characteristic)</label>
              <input
                {...(s3On ? {} : { name: "char_important" })}
                type="file"
                accept="image/*"
                disabled={!!uploadBusy}
                className="mt-2 block w-full text-sm"
                onChange={(e) => void onAssetFile("char_important", e.target.files?.[0])}
              />
              {uploadBusy === "char_important" && <p className="mt-2 text-xs text-slate-500">Uploading…</p>}
              {importantSrc && (
                <img src={importantSrc} alt="Important characteristic" className="mt-3 h-20 w-full rounded bg-white object-contain p-1" />
              )}
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 sm:col-span-2 xl:col-span-3">
              <label className="text-xs font-medium text-slate-600">FIR measured-values font (replaces Quali_1.ttf)</label>
              <p className="mt-1 text-xs text-slate-500">
                Upload a <strong>.ttf</strong> file. It is embedded in FIR previews and PDFs for measured values (same CSS family name{" "}
                <code className="rounded bg-slate-100 px-1">Quali_1</code>). Max 5&nbsp;MB.
              </p>
              <input
                {...(s3On ? {} : { name: "quali_font" })}
                type="file"
                accept=".ttf,font/ttf,application/x-font-ttf"
                disabled={!!uploadBusy}
                className="mt-2 block w-full text-sm"
                onChange={(e) => void onAssetFile("quali_font", e.target.files?.[0])}
              />
              {uploadBusy === "quali_font" && <p className="mt-2 text-xs text-slate-500">Uploading…</p>}
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <label className="inline-flex items-center gap-2 text-xs text-slate-700">
                  <input
                    type="checkbox"
                    checked={clearQualiFont}
                    onChange={(e) => setClearQualiFont(e.target.checked)}
                  />
                  Remove custom font (use bundled Quali_1 from server)
                </label>
                {(s.quali_font_configured || !!pendingS3.quali_font) && !clearQualiFont ? (
                  <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800">
                    Custom font active
                  </span>
                ) : (
                  <span className="text-xs text-slate-500">Using default bundled font when no file is uploaded.</span>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="lg:col-span-1">
          <div className="sticky top-4 rounded-lg border border-slate-200 bg-slate-50 p-4">
            <h2 className="text-sm font-semibold text-slate-800">Tips</h2>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-slate-600">
              <li>Use PNG/JPG images with transparent or white background (including Critical / Safety / Important symbols for the FIR legend).</li>
              <li>{s3On ? "Files upload when you pick them; click Save settings to store keys in the app." : "Click Save settings after selecting files."}</li>
              <li>Images are shared for all users of your company.</li>
              <li>Custom .ttf applies to FIR report measured-value fields everywhere that font is used.</li>
              {s3On && (
                <li>
                  Ensure your S3 bucket allows public read for uploaded objects (or use a CloudFront URL as PUBLIC_S3_BASE_URL) and CORS for your app
                  origin.
                </li>
              )}
            </ul>
            <button
              type="submit"
              disabled={!!uploadBusy}
              className="mt-4 w-full rounded bg-blue-700 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-60"
            >
              Save settings
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
