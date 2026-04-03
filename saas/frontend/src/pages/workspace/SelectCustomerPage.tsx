import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getWorkspaceCustomerId, setWorkspaceCustomerId, workspaceFetch } from "../../api";

type Row = { id: number; vendor_code: string; name: string };

export default function SelectCustomerPage() {
  const nav = useNavigate();
  const [rows, setRows] = useState<Row[]>([]);
  const [current, setCurrent] = useState<number | null>(getWorkspaceCustomerId());
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    workspaceFetch<Row[]>("/api/app/customers")
      .then(setRows)
      .catch((e) => setErr(e.message));
  }, []);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const fd = new FormData(e.target as HTMLFormElement);
    const id = fd.get("customer_id");
    if (id) {
      setWorkspaceCustomerId(Number(id));
      setCurrent(Number(id));
      nav("/workspace/upload");
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h1 className="text-xl font-semibold">Select customer</h1>
      <p className="mt-1 text-sm text-slate-600">Used for FIR header (vendor) when you upload invoices.</p>
      {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
      {rows.length === 0 ? (
        <p className="mt-4">
          <Link className="text-blue-700 underline" to="/workspace/customers">
            Add a customer first
          </Link>
        </p>
      ) : (
        <form onSubmit={onSubmit} className="mt-6 space-y-4">
          <select
            name="customer_id"
            className="w-full max-w-md rounded border border-slate-300 px-3 py-2 text-sm"
            defaultValue={current ?? ""}
            required
          >
            <option value="" disabled>
              Choose…
            </option>
            {rows.map((r) => (
              <option key={r.id} value={r.id}>
                {r.vendor_code} — {r.name}
              </option>
            ))}
          </select>
          <button type="submit" className="rounded bg-blue-700 px-4 py-2 text-sm text-white hover:bg-blue-800">
            Continue to upload
          </button>
        </form>
      )}
    </div>
  );
}
