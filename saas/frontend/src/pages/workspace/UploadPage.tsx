import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getWorkspaceCustomerId, setWorkspaceCustomerId, workspaceFetch, workspaceUploadInvoice } from "../../api";

type CustomerRow = { id: number; vendor_code: string; name: string };

export default function UploadPage() {
  const nav = useNavigate();
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [customers, setCustomers] = useState<CustomerRow[]>([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState<number | null>(null);

  useEffect(() => {
    workspaceFetch<CustomerRow[]>("/api/app/customers")
      .then((list) => {
        setCustomers(list);
        const ws = getWorkspaceCustomerId();
        if (list.length === 1) {
          setSelectedCustomerId(list[0].id);
          setWorkspaceCustomerId(list[0].id);
        } else if (ws != null && list.some((c) => c.id === ws)) {
          setSelectedCustomerId(ws);
        } else if (list.length > 1) {
          setSelectedCustomerId((prev) => prev ?? list[0].id);
          setWorkspaceCustomerId(list[0].id);
        }
      })
      .catch(() => setCustomers([]));
  }, []);

  useEffect(() => {
    workspaceFetch<{ ok: boolean; reason?: string; auto_customer_id?: number }>("/api/app/upload-check")
      .then((c) => {
        if (!c.ok && c.reason === "no_customers") {
          setErr("Add at least one customer before uploading.");
        }
        if (c.ok && c.auto_customer_id != null) {
          setWorkspaceCustomerId(c.auto_customer_id);
          setSelectedCustomerId(c.auto_customer_id);
        }
        if (!c.ok && c.reason === "select_customer") {
          setErr("select_customer");
        }
      })
      .catch(() => {});
  }, []);

  function onCustomerChange(id: number) {
    setSelectedCustomerId(id);
    setWorkspaceCustomerId(id);
  }

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setErr(null);
    if (customers.length > 1 && selectedCustomerId == null) {
      setErr("Select which customer this invoice belongs to before uploading.");
      return;
    }
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

  const uploadBlocked = customers.length > 1 && selectedCustomerId == null;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h1 className="text-xl font-semibold">Upload invoice details</h1>
      <p className="mt-2 text-sm text-slate-600">
        Excel .xlsx or .xls. Extra columns are ignored; only Part Number, Description, Quantity, Invoice Number, Date are
        extracted. Parts master is resolved for the customer you select below.
      </p>

      {customers.length > 1 && (
        <div className="mt-4 rounded border border-slate-200 bg-slate-50 px-3 py-3">
          <label className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-3">
            <span className="text-sm font-medium text-slate-800">Customer for this invoice</span>
            <select
              className="max-w-md rounded border border-slate-300 bg-white px-3 py-2 text-sm"
              value={selectedCustomerId ?? ""}
              onChange={(e) => onCustomerChange(Number(e.target.value))}
            >
              <option value="" disabled>
                Choose customer…
              </option>
              {customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.vendor_code} — {c.name}
                </option>
              ))}
            </select>
          </label>
          <p className="mt-2 text-xs text-slate-500">
            This sets which vendor appears on the FIR and which Parts master rows are used during inspection.
          </p>
        </div>
      )}

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
        <label
          className={`inline-block rounded px-4 py-2 text-sm font-medium text-white ${
            uploadBlocked || loading ? "cursor-not-allowed bg-slate-400" : "cursor-pointer bg-blue-700 hover:bg-blue-800"
          }`}
        >
          {loading ? "Reading…" : "Choose Excel file"}
          <input
            type="file"
            accept=".xlsx,.xls"
            className="hidden"
            onChange={onFile}
            disabled={loading || uploadBlocked}
          />
        </label>
      </div>
      <div className="mt-4 rounded border border-slate-200 bg-slate-50 p-3">
        <p className="text-sm text-slate-700">
          Don&apos;t have an Excel file?{" "}
          <button
            type="button"
            className="font-medium text-blue-700 underline"
            onClick={() => nav("/workspace/manual-entry")}
          >
            Enter rows manually
          </button>{" "}
          (useful for 1–3 new parts).
        </p>
      </div>
    </div>
  );
}
