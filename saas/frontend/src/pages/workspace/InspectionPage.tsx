import { FormEvent, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

type LocState = { rows: Record<string, unknown>[]; columns: string[]; filename?: string };

export default function InspectionPage() {
  const loc = useLocation();
  const nav = useNavigate();
  const st = loc.state as LocState | null;
  const [sel, setSel] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (st?.rows?.length) {
      setSel(new Set(st.rows.map((_, i) => i)));
    }
  }, [st?.rows]);

  if (!st?.rows?.length) {
    return (
      <div className="rounded-xl border bg-white p-6">
        <p>No rows. </p>
        <button className="text-blue-700 underline" type="button" onClick={() => nav("/workspace/upload")}>
          Upload
        </button>
      </div>
    );
  }

  const { rows, columns } = st;

  function toggle(i: number) {
    setSel((prev) => {
      const n = new Set(prev);
      if (n.has(i)) n.delete(i);
      else n.add(i);
      return n;
    });
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const picked = rows.filter((_, i) => sel.has(i));
    const finalRows = picked.length ? picked : rows;
    nav("/workspace/inspection/results", { state: { rows: finalRows } });
  }

  return (
    <form onSubmit={onSubmit} className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h1 className="text-xl font-semibold">Inspection — select rows</h1>
      <p className="mt-1 text-sm text-slate-600">Leave all checked to include every line, or uncheck to exclude.</p>
      <div className="mt-4 overflow-x-auto">
        <table className="min-w-full border-collapse text-sm">
          <thead>
            <tr className="bg-slate-100">
              <th className="border px-2 py-1">✓</th>
              {columns.map((c) => (
                <th key={c} className="border px-2 py-1 text-left">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td className="border px-2 py-1 text-center">
                  <input type="checkbox" checked={sel.has(i)} onChange={() => toggle(i)} />
                </td>
                {columns.map((c) => (
                  <td key={c} className="border px-2 py-1">
                    {String(r[c] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button type="submit" className="mt-6 rounded bg-blue-700 px-4 py-2 text-sm text-white">
        Submit to results
      </button>
    </form>
  );
}
