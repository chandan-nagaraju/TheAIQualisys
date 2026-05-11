import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { workspaceFetch } from "../../api";
import { useTheme } from "../../theme/ThemeContext";

type LocState = { rows: Record<string, unknown>[]; columns: string[]; filename?: string };

type InspectionEnrichRes = {
  rows: Record<string, unknown>[];
  customer: { id: number; vendor_code: string; name: string } | null;
  current_date: string;
};

export default function ExtractedPage() {
  const loc = useLocation();
  const nav = useNavigate();
  const { theme } = useTheme();
  const st = loc.state as LocState | null;
  const [enriched, setEnriched] = useState<InspectionEnrichRes | null>(null);
  const [enrichLoading, setEnrichLoading] = useState(false);
  const [enrichErr, setEnrichErr] = useState<string | null>(null);

  useEffect(() => {
    if (!st?.rows?.length) return;
    let cancelled = false;
    setEnriched(null);
    setEnrichLoading(true);
    setEnrichErr(null);
    workspaceFetch<InspectionEnrichRes>("/api/app/inspection/enrich", {
      method: "POST",
      body: JSON.stringify({ rows: st.rows }),
    })
      .then((res) => {
        if (!cancelled) setEnriched(res);
      })
      .catch((e) => {
        if (!cancelled) setEnrichErr(e instanceof Error ? e.message : "Could not load Parts master data");
      })
      .finally(() => {
        if (!cancelled) setEnrichLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [st?.rows]);

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

  const displayRows = useMemo(
    () => (enriched?.rows?.length ? enriched.rows : st?.rows ?? []),
    [enriched?.rows, st?.rows],
  );

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

  const { columns, filename } = st;
  /** Avoid continuing with raw rows before master lookup finishes (unless enrich failed and we fall back). */
  const continueDisabled = enrichLoading || (!enriched && !enrichErr);

  return (
    <div className={panelClass}>
      <h1 className="text-xl font-semibold">Extracted data</h1>
      {filename && <p className={`text-sm ${hintTextClass}`}>{filename}</p>}
      {enrichLoading && (
        <p className={`mt-2 text-sm ${hintTextClass}`}>Loading part descriptions from Parts master…</p>
      )}
      {enrichErr && (
        <p
          className={`mt-2 text-sm ${theme === "dark" ? "text-amber-400" : theme === "grey" ? "text-amber-800" : "text-amber-800"}`}
          role="alert"
        >
          {enrichErr} Showing values from the file only.
        </p>
      )}
      {!enrichLoading && !enrichErr && enriched && (
        <p className={`mt-2 text-sm ${hintTextClass}`}>
          Descriptions and drawing rev for matched part numbers come from Parts master.
        </p>
      )}
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
            {displayRows.map((r, i) => (
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
        disabled={continueDisabled}
        className={
          continueDisabled
            ? theme === "grey"
              ? "mt-6 rounded bg-zinc-400 px-4 py-2 text-sm text-white"
              : "mt-6 cursor-not-allowed rounded bg-slate-400 px-4 py-2 text-sm text-white"
            : continueBtnClass
        }
        onClick={() => nav("/workspace/inspection", { state: { rows: displayRows, columns, filename: st.filename } })}
      >
        Continue to inspection
      </button>
    </div>
  );
}
