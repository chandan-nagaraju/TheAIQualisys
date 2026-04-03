import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { setWorkspaceCustomerId, workspaceFetch, workspaceUploadInvoice } from "../../api";

export default function UploadPage() {
  const nav = useNavigate();
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    workspaceFetch<{ ok: boolean; reason?: string; auto_customer_id?: number }>("/api/app/upload-check")
      .then((c) => {
        if (!c.ok && c.reason === "no_customers") {
          setErr("Add at least one customer before uploading.");
        }
        if (c.ok && c.auto_customer_id != null) {
          setWorkspaceCustomerId(c.auto_customer_id);
        }
        if (!c.ok && c.reason === "select_customer") {
          setErr("select_customer");
        }
      })
      .catch(() => {});
  }, []);

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setErr(null);
    setLoading(true);
    try {
      const pre = await workspaceFetch<{ ok: boolean; reason?: string }>("/api/app/upload-check");
      if (!pre.ok && pre.reason === "select_customer") {
        setErr("select_customer");
        setLoading(false);
        return;
      }
      const res = await workspaceUploadInvoice(file);
      nav("/workspace/extracted", { state: { rows: res.rows, columns: res.columns, filename: res.filename } });
    } catch (ex) {
      const msg = ex instanceof Error ? ex.message : "Upload failed";
      if (msg.includes("select_customer")) setErr("select_customer");
      else setErr(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h1 className="text-xl font-semibold">Upload invoice</h1>
      <p className="mt-2 text-sm text-slate-600">Excel .xlsx or .xls — same column mapping as the legacy app.</p>
      {err === "select_customer" && (
        <p className="mt-4 rounded bg-amber-50 p-3 text-sm text-amber-900">
          Please{" "}
          <Link className="font-medium underline" to="/workspace/select-customer">
            select a customer
          </Link>{" "}
          first (you have more than one).
        </p>
      )}
      {err && err !== "select_customer" && <p className="mt-4 text-sm text-red-600">{err}</p>}
      <div className="mt-6">
        <label className="inline-block cursor-pointer rounded bg-blue-700 px-4 py-2 text-sm font-medium text-white hover:bg-blue-800">
          {loading ? "Reading…" : "Choose Excel file"}
          <input type="file" accept=".xlsx,.xls" className="hidden" onChange={onFile} disabled={loading} />
        </label>
      </div>
    </div>
  );
}
