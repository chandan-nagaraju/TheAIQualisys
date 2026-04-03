import { useLocation, useNavigate } from "react-router-dom";

type LocState = { rows: Record<string, unknown>[]; columns: string[]; filename?: string };

export default function ExtractedPage() {
  const loc = useLocation();
  const nav = useNavigate();
  const st = loc.state as LocState | null;
  if (!st?.rows?.length) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <p>No extracted data. </p>
        <button type="button" className="mt-2 text-blue-700 underline" onClick={() => nav("/workspace/upload")}>
          Upload an invoice
        </button>
      </div>
    );
  }

  const { rows, columns, filename } = st;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h1 className="text-xl font-semibold">Extracted data</h1>
      {filename && <p className="text-sm text-slate-500">{filename}</p>}
      <div className="mt-4 overflow-x-auto">
        <table className="min-w-full border-collapse text-sm">
          <thead>
            <tr className="bg-slate-100">
              {columns.map((c) => (
                <th key={c} className="border border-slate-200 px-2 py-1 text-left">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                {columns.map((c) => (
                  <td key={c} className="border border-slate-200 px-2 py-1">
                    {String(r[c] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button
        type="button"
        className="mt-6 rounded bg-blue-700 px-4 py-2 text-sm text-white hover:bg-blue-800"
        onClick={() => nav("/workspace/inspection", { state: { rows, columns } })}
      >
        Continue to inspection
      </button>
    </div>
  );
}
