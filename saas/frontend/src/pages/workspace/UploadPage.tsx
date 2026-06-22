import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getWorkspaceCustomerId, setWorkspaceCustomerId, workspaceFetch, workspaceUploadInvoice } from "../../api";
import { clearInspectionSession } from "../../workspace/inspectionSession";

type CustomerRow = { id: number; vendor_code: string; name: string };

export default function UploadPage() {
  const nav = useNavigate();
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [customers, setCustomers] = useState<CustomerRow[]>([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState<number | null>(null);
  /** How many manual FIR rows to open on the manual-entry page (clamped there as well). */
  const [manualReportCount, setManualReportCount] = useState(3);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [list, c] = await Promise.all([
        workspaceFetch<CustomerRow[]>("/api/app/customers").catch(() => [] as CustomerRow[]),
        workspaceFetch<{ ok: boolean; reason?: string; auto_customer_id?: number }>("/api/app/upload-check").catch(
          () => null,
        ),
      ]);
      if (cancelled) return;
      setCustomers(list);
      const ws = getWorkspaceCustomerId();
      if (list.length === 1) {
        setSelectedCustomerId(list[0].id);
        setWorkspaceCustomerId(list[0].id);
      } else if (ws != null && list.some((x) => x.id === ws)) {
        setSelectedCustomerId(ws);
      } else if (list.length > 1) {
        setSelectedCustomerId((prev) => prev ?? list[0].id);
        setWorkspaceCustomerId(list[0].id);
      }
      if (c) {
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
      }
    })();
    return () => {
      cancelled = true;
    };
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
      clearInspectionSession();
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

  const clampedManualCount = Math.min(50, Math.max(1, Math.floor(manualReportCount) || 1));

  function goManualEntry() {
    nav("/workspace/manual-entry", { state: { desiredRowCount: clampedManualCount } });
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h1 className="text-xl font-semibold">Upload invoice details</h1>
      <p className="mt-2 text-sm text-slate-600">
        Upload an Excel invoice (<span className="font-mono text-xs">.xlsx</span> or{" "}
        <span className="font-mono text-xs">.xls</span>). If you have more than one customer, choose who this
        invoice is for below.
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
          <p className="mt-2 text-xs text-slate-500">This customer appears on your FIR and matches parts in your library.</p>
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
      <div className="mt-6 border-t border-slate-200 pt-4">
        <p className="text-sm font-medium text-slate-800">Manual entry (no Excel)</p>
        <p className="mt-1 text-xs text-slate-500">
          Set how many FIR line items you need, then fill the table on the next screen.
        </p>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <label className="text-sm text-slate-700">
            <span className="block text-slate-600">Number of reports</span>
            <input
              type="number"
              min={1}
              max={50}
              className="mt-1 w-24 rounded border border-slate-300 bg-white px-2 py-1.5 tabular-nums"
              value={manualReportCount}
              onChange={(e) => setManualReportCount(Number(e.target.value))}
            />
          </label>
          <button
            type="button"
            className="rounded border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50"
            onClick={goManualEntry}
          >
            Continue without Excel
          </button>
        </div>
      </div>
    </div>
  );
}
