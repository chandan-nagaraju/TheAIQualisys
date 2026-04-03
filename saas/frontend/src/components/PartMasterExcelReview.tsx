
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
  onConfirm: () => void;
  onCancel: () => void;
  busy?: boolean;
};

function AdTable({ title, rows }: { title: string; rows: AdRow[] }) {
  if (!rows?.length) {
    return (
      <div className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500">
        {title}: no rows
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded border border-slate-200">
      <p className="border-b border-slate-200 bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-700">{title}</p>
      <table className="min-w-full text-left text-xs">
        <thead>
          <tr className="border-b border-slate-200 bg-white text-slate-600">
            <th className="px-2 py-1">Parameter</th>
            <th className="px-2 py-1">Specification</th>
            <th className="px-2 py-1">Special char</th>
            <th className="px-2 py-1">Method</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-slate-100">
              <td className="px-2 py-1 font-medium text-slate-800">{r.parameter}</td>
              <td className="px-2 py-1 text-slate-700">{r.specification ?? "—"}</td>
              <td className="px-2 py-1 text-slate-600">{r.special_char ?? "—"}</td>
              <td className="px-2 py-1 text-slate-600">{r.method_of_inspection ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function PartMasterExcelReview({ bundle, fileLabel, onConfirm, onCancel, busy }: Props) {
  const n = bundle.parts?.length ?? 0;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center">
      <div
        className="flex max-h-[90vh] w-full max-w-4xl flex-col rounded-xl border border-slate-200 bg-white shadow-xl"
        role="dialog"
        aria-labelledby="excel-review-title"
      >
        <div className="border-b border-slate-200 px-4 py-3">
          <h2 id="excel-review-title" className="text-lg font-semibold text-slate-900">
            Review part master from Excel
          </h2>
          <p className="mt-1 text-sm text-slate-600">
            File: <span className="font-mono text-slate-800">{fileLabel}</span> —{" "}
            <strong className="text-slate-800">{n}</strong> part{n === 1 ? "" : "s"} will be saved (same rules as JSON
            bundle: existing parts are updated; A–D rows replaced).
          </p>
          <p className="mt-1 text-xs text-slate-500">
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
              {bundle.parts.map((sl, idx) => (
                <div key={`${sl.part.part_no}-${idx}`} className="rounded-lg border border-slate-200 bg-slate-50/80 p-3">
                  <h3 className="text-sm font-semibold text-slate-900">
                    Part <span className="font-mono text-blue-800">{sl.part.part_no}</span>
                  </h3>
                  <dl className="mt-2 grid gap-1 text-xs text-slate-700 sm:grid-cols-2">
                    <div>
                      <dt className="text-slate-500">Drawing rev</dt>
                      <dd className="font-mono">{sl.part.drawing_rev || "—"}</dd>
                    </div>
                    <div className="sm:col-span-2">
                      <dt className="text-slate-500">Description</dt>
                      <dd>{sl.part.description || "—"}</dd>
                    </div>
                  </dl>
                  <div className="mt-3 grid gap-3">
                    <AdTable title="Section A — dimensions" rows={sl.spec_rows ?? []} />
                    <AdTable title="Section B — customer complaints / checkpoints" rows={sl.ccp_rows ?? []} />
                    {sl.material_rows?.length ? (
                      <div className="rounded border border-slate-200">
                        <p className="border-b border-slate-200 bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-700">
                          Section C — material
                        </p>
                        <ul className="list-inside list-disc px-2 py-2 text-xs text-slate-800">
                          {sl.material_rows.map((m, i) => (
                            <li key={i} className="font-mono">
                              {m.material_grade}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : (
                      <div className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500">
                        Section C — material: no rows
                      </div>
                    )}
                    <AdTable title="Section D — surface coating" rows={sl.coating_rows ?? []} />
                  </div>
                </div>
              ))}
            </div>
          )}

          <details className="mt-4 rounded border border-slate-200 bg-white p-2">
            <summary className="cursor-pointer text-xs font-medium text-slate-600">Raw JSON (advanced)</summary>
            <pre className="mt-2 max-h-48 overflow-auto rounded bg-slate-50 p-2 text-[10px] text-slate-800">
              {JSON.stringify(bundle, null, 2)}
            </pre>
          </details>
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-slate-200 bg-slate-50 px-4 py-3">
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
            onClick={onConfirm}
            disabled={busy || n === 0}
          >
            {busy ? "Saving…" : "OK — save to part master"}
          </button>
        </div>
      </div>
    </div>
  );
}
