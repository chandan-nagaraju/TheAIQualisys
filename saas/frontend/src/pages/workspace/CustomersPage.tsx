import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { workspaceFetch } from "../../api";

type Row = { id: number; vendor_code: string; name: string };

export default function CustomersPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [vendor_code, setVendorCode] = useState("");
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    setRows(await workspaceFetch<Row[]>("/api/app/customers"));
  }

  useEffect(() => {
    load().catch((e) => setErr(String(e.message)));
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    try {
      await workspaceFetch("/api/app/customers", {
        method: "POST",
        body: JSON.stringify({ vendor_code, name }),
      });
      setVendorCode("");
      setName("");
      await load();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Failed");
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Customers / vendors</h1>
        <Link className="text-sm text-blue-700 hover:underline" to="/workspace/select-customer">
          Select customer for session
        </Link>
      </div>
      {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
      <form onSubmit={onSubmit} className="mt-6 flex flex-wrap items-end gap-3 border-b border-slate-100 pb-6">
        <div>
          <label className="block text-xs text-slate-500">Vendor code</label>
          <input
            className="mt-1 rounded border border-slate-300 px-2 py-1.5 text-sm"
            value={vendor_code}
            onChange={(e) => setVendorCode(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="block text-xs text-slate-500">Name</label>
          <input
            className="mt-1 rounded border border-slate-300 px-2 py-1.5 text-sm"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </div>
        <button type="submit" className="rounded bg-blue-700 px-4 py-2 text-sm font-medium text-white hover:bg-blue-800">
          Add customer
        </button>
      </form>
      <ul className="mt-6 divide-y divide-slate-100">
        {rows.map((r) => (
          <li key={r.id} className="py-3 text-sm">
            <span className="font-mono text-slate-800">{r.vendor_code}</span>
            <span className="mx-2 text-slate-400">—</span>
            <span>{r.name}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
