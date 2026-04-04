import { useLocation, useNavigate } from "react-router-dom";
import { useTheme } from "../../theme/ThemeContext";

type LocState = { rows: Record<string, unknown>[]; columns: string[]; filename?: string };

export default function ExtractedPage() {
  const loc = useLocation();
  const nav = useNavigate();
  const { theme } = useTheme();
  const st = loc.state as LocState | null;

  const panelClass =
    theme === "light"
      ? "rounded-xl border border-slate-200 bg-white p-6 text-slate-900 shadow-sm"
      : theme === "grey"
        ? "rounded-xl border border-zinc-300 bg-zinc-50 p-6 text-zinc-900 shadow-sm"
        : "rounded-xl border border-slate-700 bg-slate-900 p-6 text-slate-100 shadow-sm";

  const hintTextClass =
    theme === "light" ? "text-slate-500" : theme === "grey" ? "text-zinc-600" : "text-slate-300";

  const tableOuterClass =
    theme === "light"
      ? "mt-4 overflow-x-auto rounded-lg border border-slate-200"
      : theme === "grey"
        ? "mt-4 overflow-x-auto rounded-lg border border-zinc-300"
        : "mt-4 overflow-x-auto rounded-lg border border-slate-700";

  const theadRowClass =
    theme === "light" ? "bg-slate-100 text-slate-900" : theme === "grey" ? "bg-zinc-200 text-zinc-900" : "bg-slate-800 text-slate-100";

  const thClass =
    theme === "light"
      ? "border border-slate-200 px-2 py-1 text-left font-semibold text-slate-900"
      : theme === "grey"
        ? "border border-zinc-300 px-2 py-1 text-left font-semibold text-zinc-900"
        : "border border-slate-700 px-2 py-1 text-left font-semibold text-slate-100";

  const tdClass =
    theme === "light"
      ? "border border-slate-200 px-2 py-1 text-slate-800"
      : theme === "grey"
        ? "border border-zinc-300 px-2 py-1 text-zinc-800"
        : "border border-slate-700 px-2 py-1 text-slate-200";

  const rowAltClass = theme === "light" ? "odd:bg-white even:bg-slate-50" : theme === "grey" ? "odd:bg-zinc-50 even:bg-zinc-100/70" : "odd:bg-slate-900 even:bg-slate-800/70";

  const continueBtnClass =
    theme === "light"
      ? "mt-6 rounded bg-blue-700 px-4 py-2 text-sm text-white hover:bg-blue-800"
      : theme === "grey"
        ? "mt-6 rounded bg-zinc-700 px-4 py-2 text-sm text-white hover:bg-zinc-800"
        : "mt-6 rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-500";

  const linkClass = theme === "dark" ? "mt-2 text-blue-300 underline" : "mt-2 text-blue-700 underline";

  if (!st?.rows?.length) {
    return (
      <div className={panelClass}>
        <p>No extracted data. </p>
        <div className="mt-2 flex flex-wrap gap-3">
          <button type="button" className={linkClass} onClick={() => nav("/workspace/upload")}>
            Upload an invoice
          </button>
          <button type="button" className={linkClass} onClick={() => nav("/workspace/manual-entry")}>
            Enter rows manually
          </button>
        </div>
      </div>
    );
  }

  const { rows, columns, filename } = st;

  return (
    <div className={panelClass}>
      <h1 className="text-xl font-semibold">Extracted data</h1>
      {filename && <p className={`text-sm ${hintTextClass}`}>{filename}</p>}
      <div className={tableOuterClass}>
        <table className="min-w-full border-collapse text-sm">
          <thead>
            <tr className={theadRowClass}>
              {columns.map((c) => (
                <th key={c} className={thClass}>
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className={rowAltClass}>
                {columns.map((c) => (
                  <td key={c} className={tdClass}>
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
        className={continueBtnClass}
        onClick={() => nav("/workspace/inspection", { state: { rows, columns } })}
      >
        Continue to inspection
      </button>
    </div>
  );
}
