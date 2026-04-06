
import { useEffect, useState } from "react";

/** Parsed bundle from Excel preview (matches fir_part_master_bundle_v1). */
export type PartMasterBundle = {
  format: string;
  parts: PartSlice[];
};

export type PartSlice = {
  part: { part_no: string; drawing_rev?: string | null; description?: string | null };
  spec_rows?: AdRow[];
  ccp_rows?: AdRow[];
  material_rows?: { material_grade: string }[];
  coating_rows?: AdRow[];
};

type AdRow = {
  parameter: string;
  specification?: string | null;
  special_char?: string | null;
  method_of_inspection?: string | null;
};

type Props = {
  bundle: PartMasterBundle;
  fileLabel: string;
  onConfirm: (bundle: PartMasterBundle) => void;
  onCancel: () => void;
  busy?: boolean;
};

function AdTable({
  title,
  rows,
  onDeleteRow,
  tableClass,
  headRowClass,
  bodyCellClass,
  mutedCellClass,
  noRowsClass,
}: {
  title: string;
  rows: AdRow[];
  onDeleteRow?: (rowIndex: number) => void;
  tableClass: string;
  headRowClass: string;
  bodyCellClass: string;
  mutedCellClass: string;
  noRowsClass: string;
}) {
  if (!rows?.length) {
    return (
      <div className={noRowsClass}>
        {title}: no rows
      </div>
    );
  }
  return (
    <div className={tableClass}>
      <p className={`border-b px-2 py-1 text-xs font-semibold ${headRowClass}`}>{title}</p>
      <table className="min-w-full text-left text-xs">
        <thead>
          <tr className={`border-b ${headRowClass}`}>
            <th className="px-2 py-1">Parameter</th>
            <th className="px-2 py-1">Specification</th>
            <th className="px-2 py-1">Special char</th>
            <th className="px-2 py-1">Method</th>
            {onDeleteRow && <th className="px-2 py-1 text-right">Action</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={`border-b ${bodyCellClass}`}>
              <td className={`px-2 py-1 font-medium ${bodyCellClass}`}>{r.parameter}</td>
              <td className={`px-2 py-1 ${bodyCellClass}`}>{r.specification ?? "—"}</td>
              <td className={`px-2 py-1 ${mutedCellClass}`}>{r.special_char ?? "—"}</td>
              <td className={`px-2 py-1 ${mutedCellClass}`}>{r.method_of_inspection ?? "—"}</td>
              {onDeleteRow && (
                <td className="px-2 py-1 text-right">
                  <button
                    type="button"
                    className="rounded border border-red-200 bg-red-50 px-2 py-0.5 text-[11px] font-medium text-red-700 hover:bg-red-100"
                    onClick={() => onDeleteRow(i)}
                  >
                    Remove
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function PartMasterExcelReview({ bundle, fileLabel, onConfirm, onCancel, busy }: Props) {
  const [draft, setDraft] = useState<PartMasterBundle>(bundle);

  useEffect(() => {
    setDraft(bundle);
  }, [bundle]);

  const n = draft.parts?.length ?? 0;
  const rootClass = "rounded-xl border border-slate-300 bg-white text-slate-900 shadow-2xl";
  const headerClass = "border-b border-slate-300 bg-slate-50";
  const partCardClass = "rounded-lg border border-slate-300 bg-slate-50 p-3";
  const titleClass = "text-slate-900";
  const subClass = "text-slate-700";
  const mutedClass = "text-slate-600";
  const tableWrapClass = "overflow-x-auto rounded border border-slate-300 bg-white";
  const tableHeadClass = "border-slate-300 bg-slate-100 text-slate-800";
  const tableBodyClass = "border-slate-200 text-slate-800";
  const tableMutedClass = "text-slate-700";
  const noRowsClass = "rounded border border-slate-300 bg-slate-100 px-3 py-2 text-xs text-slate-700";
  const footerClass = "border-t border-slate-300 bg-slate-100";

  function removePart(partIndex: number) {
    setDraft((prev) => {
      const next = JSON.parse(JSON.stringify(prev)) as PartMasterBundle;
      next.parts.splice(partIndex, 1);
      return next;
    });
  }

  function removeAdRow(partIndex: number, key: "spec_rows" | "ccp_rows" | "coating_rows", rowIndex: number) {
    setDraft((prev) => {
      const next = JSON.parse(JSON.stringify(prev)) as PartMasterBundle;
      const rows = (next.parts[partIndex]?.[key] as AdRow[] | undefined) ?? [];
      rows.splice(rowIndex, 1);
      next.parts[partIndex][key] = rows;
      return next;
    });
  }

  function removeMaterialRow(partIndex: number, rowIndex: number) {
    setDraft((prev) => {
      const next = JSON.parse(JSON.stringify(prev)) as PartMasterBundle;
      const rows = next.parts[partIndex]?.material_rows ?? [];
      rows.splice(rowIndex, 1);
      next.parts[partIndex].material_rows = rows;
      return next;
    });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center">
      <div
        className={`flex max-h-[90vh] w-full max-w-4xl flex-col ${rootClass}`}
        role="dialog"
        aria-labelledby="excel-review-title"
      >
        <div className={`px-4 py-3 ${headerClass}`}>
          <h2 id="excel-review-title" className={`text-lg font-semibold ${titleClass}`}>
            Review part master from Excel
          </h2>
          <p className={`mt-1 text-sm ${subClass}`}>
            File: <span className="font-mono text-slate-900">{fileLabel}</span> —{" "}
            <strong className="text-slate-900">{n}</strong> part{n === 1 ? "" : "s"} will be saved (same rules as JSON
            bundle: existing parts are updated; A–D rows replaced).
          </p>
          <p className={`mt-1 text-xs font-medium ${subClass}`}>
            Remove unwanted parts/rows here before saving.
          </p>
          <p className={`mt-1 text-xs ${mutedClass}`}>
            Only <strong>specification / method</strong> columns are stored in part master — not invoice, qty, or
            measured values. Align your Excel with the template sheets (Parts, Section_A–D).
          </p>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
          {n === 0 ? (
            <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
              No parts were detected. Use the <strong>Parts</strong> sheet (or section rows with Part Number), then
              upload again.
            </p>
          ) : (
            <div className="space-y-6">
              {draft.parts.map((sl, idx) => (
                <div key={`${sl.part.part_no}-${idx}`} className={partCardClass}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className={`text-sm font-semibold ${titleClass}`}>
                      Part <span className="font-mono text-blue-800">{sl.part.part_no}</span>
                    </h3>
                    <button
                      type="button"
                      className="rounded border border-red-200 bg-red-50 px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-100"
                      onClick={() => removePart(idx)}
                    >
                      Remove part
                    </button>
                  </div>
                  <dl className={`mt-2 grid gap-1 text-xs ${subClass} sm:grid-cols-2`}>
                    <div>
                      <dt className={mutedClass}>Drawing rev</dt>
                      <dd className="font-mono">{sl.part.drawing_rev || "—"}</dd>
                    </div>
                    <div className="sm:col-span-2">
                      <dt className={mutedClass}>Description</dt>
                      <dd>{sl.part.description || "—"}</dd>
                    </div>
                  </dl>
                  <div className="mt-3 grid gap-3">
                    <AdTable
                      title="Section A — dimensions"
                      rows={sl.spec_rows ?? []}
                      onDeleteRow={(rowIndex) => removeAdRow(idx, "spec_rows", rowIndex)}
                      tableClass={tableWrapClass}
                      headRowClass={tableHeadClass}
                      bodyCellClass={tableBodyClass}
                      mutedCellClass={tableMutedClass}
                      noRowsClass={noRowsClass}
                    />
                    <AdTable
                      title="Section B — customer complaints / checkpoints"
                      rows={sl.ccp_rows ?? []}
                      onDeleteRow={(rowIndex) => removeAdRow(idx, "ccp_rows", rowIndex)}
                      tableClass={tableWrapClass}
                      headRowClass={tableHeadClass}
                      bodyCellClass={tableBodyClass}
                      mutedCellClass={tableMutedClass}
                      noRowsClass={noRowsClass}
                    />
                    {sl.material_rows?.length ? (
                      <div className={tableWrapClass}>
                        <p className={`border-b px-2 py-1 text-xs font-semibold ${tableHeadClass}`}>
                          Section C — material
                        </p>
                        <ul className="px-2 py-2 text-xs text-slate-800">
                          {sl.material_rows.map((m, i) => (
                            <li key={i} className="mb-1 flex items-center justify-between gap-2">
                              <span className="font-mono">{m.material_grade}</span>
                              <button
                                type="button"
                                className="rounded border border-red-200 bg-red-50 px-2 py-0.5 text-[11px] font-medium text-red-700 hover:bg-red-100"
                                onClick={() => removeMaterialRow(idx, i)}
                              >
                                Remove
                              </button>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : (
                      <div className={noRowsClass}>
                        Section C — material: no rows
                      </div>
                    )}
                    <AdTable
                      title="Section D — surface coating"
                      rows={sl.coating_rows ?? []}
                      onDeleteRow={(rowIndex) => removeAdRow(idx, "coating_rows", rowIndex)}
                      tableClass={tableWrapClass}
                      headRowClass={tableHeadClass}
                      bodyCellClass={tableBodyClass}
                      mutedCellClass={tableMutedClass}
                      noRowsClass={noRowsClass}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}

          <details className="mt-4 rounded border border-slate-300 bg-white p-2">
            <summary className={`cursor-pointer text-xs font-medium ${subClass}`}>Raw JSON (advanced)</summary>
            <pre className="mt-2 max-h-48 overflow-auto rounded bg-slate-100 p-2 text-[10px] text-slate-900">
              {JSON.stringify(draft, null, 2)}
            </pre>
          </details>
        </div>

        <div className={`flex flex-wrap items-center justify-end gap-2 px-4 py-3 ${footerClass}`}>
          <button
            type="button"
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-100"
            onClick={onCancel}
            disabled={busy}
          >
            Cancel
          </button>
          <button
            type="button"
            className="rounded-lg bg-emerald-600 px-5 py-2 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
            onClick={() => onConfirm(draft)}
            disabled={busy || n === 0}
          >
            {busy ? "Saving…" : "OK — save to part master"}
          </button>
        </div>
      </div>
    </div>
  );
}
