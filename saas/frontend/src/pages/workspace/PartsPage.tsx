import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  downloadWorkspacePdf,
  openWorkspacePdfInNewTab,
  workspaceDownloadBlob,
  workspaceFetch,
  workspacePostFile,
} from "../../api";
import PartMasterExcelReview, { type PartMasterBundle } from "../../components/PartMasterExcelReview";

type Row = {
  part_id: number;
  part_no: string;
  drawing_rev: string | null;
  description: string | null;
  has_drawing?: boolean;
};

export default function PartsPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [part_no, setPartNo] = useState("");
  const [drawing_rev, setDrawingRev] = useState("");
  const [description, setDescription] = useState("");
  const [editingPartId, setEditingPartId] = useState<number | null>(null);
  const [originalDrawingRev, setOriginalDrawingRev] = useState<string | null>(null);
  const [revisionReason, setRevisionReason] = useState("");
  const [pendingPdf, setPendingPdf] = useState<File | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const [pendingExcelBundle, setPendingExcelBundle] = useState<PartMasterBundle | null>(null);
  const [pendingExcelLabel, setPendingExcelLabel] = useState("");
  const [excelBusy, setExcelBusy] = useState(false);
  const importRef = useRef<HTMLInputElement>(null);
  const excelRef = useRef<HTMLInputElement>(null);

  async function load() {
    setRows(await workspaceFetch<Row[]>("/api/app/parts"));
  }

  useEffect(() => {
    load().catch((e) => setErr(e.message));
  }, []);

  const filterQ = part_no.trim().toLowerCase();
  const visibleRows = useMemo(() => {
    if (!filterQ) return rows;
    return rows.filter((r) => r.part_no.toLowerCase().includes(filterQ));
  }, [rows, filterQ]);

  async function downloadAll() {
    setErr(null);
    setImportMsg(null);
    try {
      const blob = await workspaceDownloadBlob("/api/app/parts/export-all");
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "fir_all_parts_master.json";
      a.click();
      URL.revokeObjectURL(url);
      setImportMsg("Download started: fir_all_parts_master.json (import this file here when needed).");
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Download failed");
    }
  }

  async function onImportFile(file: File | undefined) {
    if (!file) return;
    setErr(null);
    setImportMsg(null);
    try {
      const text = await file.text();
      const data = JSON.parse(text) as { format?: string; parts?: unknown[] };
      if (data.format === "fir_part_master_bundle_v1") {
        await workspaceFetch("/api/app/parts/import-bundle", {
          method: "POST",
          body: JSON.stringify(data),
        });
        const n = Array.isArray(data.parts) ? data.parts.length : 0;
        setImportMsg(`Imported ${n} part(s) from bundle.`);
      } else if (data.format === "fir_part_master_v1") {
        const r = await workspaceFetch<{ part_id: number; part_no: string }>("/api/app/parts/import-master", {
          method: "POST",
          body: JSON.stringify(data),
        });
        setImportMsg(`Imported “${r.part_no}” — open Edit A–D to verify.`);
      } else {
        setErr('Unknown JSON format. Use “Download all parts” or a single-part export (format fir_part_master_v1).');
        return;
      }
      await load();
    } catch (ex) {
      if (ex instanceof SyntaxError) setErr("File is not valid JSON.");
      else setErr(ex instanceof Error ? ex.message : "Import failed");
    }
  }

  async function onExcelPickForReview(file: File | undefined) {
    if (!file) return;
    setErr(null);
    setImportMsg(null);
    setExcelBusy(true);
    try {
      const endpoint = "/api/app/parts/preview-excel-master";
      const bundle = await workspacePostFile<PartMasterBundle>(endpoint, file);
      setPendingExcelLabel(file.name);
      setPendingExcelBundle(bundle);
      if (!bundle.parts?.length) {
        setErr("Excel parsed but no parts were found — check the Parts sheet and Part Number column.");
      }
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Excel preview failed");
    } finally {
      setExcelBusy(false);
    }
  }

  async function confirmExcelImport(nextBundle?: PartMasterBundle) {
    const bundle = nextBundle ?? pendingExcelBundle;
    if (!bundle?.parts?.length) return;
    setErr(null);
    setImportMsg(null);
    setExcelBusy(true);
    try {
      await workspaceFetch("/api/app/parts/import-bundle", {
        method: "POST",
        body: JSON.stringify(bundle),
      });
      setImportMsg(`Saved ${bundle.parts.length} part(s) from Excel to part master.`);
      setPendingExcelBundle(null);
      setPendingExcelLabel("");
      await load();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Save failed");
    } finally {
      setExcelBusy(false);
    }
  }

  function cancelExcelReview() {
    if (excelBusy) return;
    setPendingExcelBundle(null);
    setPendingExcelLabel("");
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    const nextRev = drawing_rev || null;
    if (
      editingPartId != null &&
      (originalDrawingRev ?? "") !== (nextRev ?? "") &&
      !revisionReason.trim()
    ) {
      setErr("Reason for revision change is required when you change drawing revision.");
      return;
    }
    try {
      const r = await workspaceFetch<{ part_id: number }>("/api/app/parts", {
        method: "POST",
        body: JSON.stringify({
          part_no,
          drawing_rev: nextRev,
          description: description || null,
          part_id: editingPartId,
          revision_change_reason: revisionReason.trim() || null,
        }),
      });
      if (pendingPdf) {
        await workspacePostFile(`/api/app/parts/${r.part_id}/drawing`, pendingPdf, "file");
      }
      setPartNo("");
      setDrawingRev("");
      setDescription("");
      setEditingPartId(null);
      setOriginalDrawingRev(null);
      setRevisionReason("");
      setPendingPdf(null);
      await load();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Failed");
    }
  }

  function startEdit(r: Row) {
    setEditingPartId(r.part_id);
    setOriginalDrawingRev(r.drawing_rev ?? null);
    setPartNo(r.part_no);
    setDrawingRev(r.drawing_rev ?? "");
    setDescription(r.description ?? "");
    setRevisionReason("");
    setPendingPdf(null);
    setErr(null);
  }

  function cancelEdit() {
    setEditingPartId(null);
    setOriginalDrawingRev(null);
    setPartNo("");
    setDrawingRev("");
    setDescription("");
    setRevisionReason("");
    setPendingPdf(null);
  }

  async function viewDrawing(partId: number) {
    setErr(null);
    try {
      openWorkspacePdfInNewTab(`/api/app/parts/${partId}/drawing`);
    } catch (ex) {
      const msg = ex instanceof Error ? ex.message : "View failed";
      setErr(
        `${msg} You can add a PDF from the part detail page (open the part number) or use “Add PDF” below.`,
      );
      void load();
    }
  }

  async function downloadDrawing(partId: number, partNo: string) {
    setErr(null);
    try {
      const safe = partNo.replace(/[^\w.\-]+/g, "_").slice(0, 120) || "part";
      downloadWorkspacePdf(`/api/app/parts/${partId}/drawing?download=true`, `${safe}_drawing.pdf`);
    } catch (ex) {
      const msg = ex instanceof Error ? ex.message : "Download failed";
      setErr(
        `${msg} Add or replace the drawing from the part detail page or “Add PDF” below.`,
      );
      void load();
    }
  }

  async function downloadOne(partId: number, partNo: string) {
    setErr(null);
    try {
      const blob = await workspaceDownloadBlob(`/api/app/parts/${partId}/export`);
      const safe = partNo.replace(/[^\w.\-]+/g, "_").slice(0, 120) || "part";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `fir_part_master_${safe}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Download failed");
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
      <h1 className="text-xl font-semibold text-slate-900">Parts master</h1>
      <p className="mt-2 text-sm text-slate-600">
        Same layout as legacy Flask: filter the table with the part number field, add or edit core fields, then open{" "}
        <strong>Edit A–D</strong> for dimension / complaint / material / coating rows.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 sm:gap-3 sm:px-4">
        <button
          type="button"
          className="w-full rounded bg-blue-700 px-4 py-2 text-sm font-medium text-white hover:bg-blue-800 sm:w-auto"
          onClick={() => void downloadAll()}
        >
          Download all parts (full A–D JSON)
        </button>
        <input
          ref={importRef}
          type="file"
          accept=".json,application/json"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            void onImportFile(f);
          }}
        />
        <button
          type="button"
          className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 hover:bg-slate-100 sm:w-auto"
          onClick={() => importRef.current?.click()}
        >
          Import JSON (bundle or one part)
        </button>
        <input
          ref={excelRef}
          type="file"
          accept=".xlsx,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            void onExcelPickForReview(f);
          }}
        />
        <button
          type="button"
          className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 hover:bg-slate-100 disabled:opacity-50 sm:w-auto"
          onClick={() => excelRef.current?.click()}
          disabled={excelBusy}
        >
          {excelBusy ? "Reading Excel…" : "Upload Excel (first sheet only, review before save)"}
        </button>
      </div>
      <p className="mt-2 text-xs text-slate-500">
        <strong>Excel:</strong> sheets <code className="rounded bg-slate-100 px-1">Parts</code>,{" "}
        <code className="rounded bg-slate-100 px-1">Section_A</code>–<code className="rounded bg-slate-100 px-1">D</code>{" "}
        (dimensions, CCP, material grade, coating). After upload you review extracted part master fields;{" "}
        <strong>OK</strong> saves the same way as JSON <code className="rounded bg-slate-100 px-1">import-bundle</code>. See{" "}
        <code className="rounded bg-slate-100 px-1">docs/PART_MASTER_EXCEL.md</code>.
      </p>
      <p className="mt-1 text-xs text-slate-500">
        <strong>JSON</strong> import matches legacy bundle / single-part formats.
      </p>

      {importMsg && <p className="mt-2 text-sm text-green-700">{importMsg}</p>}
      {err && <p className="mt-2 text-sm text-red-600">{err}</p>}

      <form onSubmit={onSubmit} className="mt-6 border-b border-slate-100 pb-6">
        <h2 className="text-sm font-semibold text-slate-800">{editingPartId != null ? "Update part" : "New part"}</h2>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <div>
            <label className="text-xs text-slate-500">Part number * (also filters table below)</label>
            <input
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
              value={part_no}
              onChange={(e) => setPartNo(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="text-xs text-slate-500">Drawing rev</label>
            <input
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
              value={drawing_rev}
              onChange={(e) => setDrawingRev(e.target.value)}
            />
          </div>
          <div className="md:col-span-2">
            <label className="text-xs text-slate-500">Description</label>
            <input
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div className="md:col-span-2">
            <label className="text-xs text-slate-500">Part drawing (PDF)</label>
            <input
              type="file"
              accept="application/pdf,.pdf"
              className="mt-1 block w-full text-sm text-slate-700 file:mr-3 file:rounded file:border file:border-slate-300 file:bg-white file:px-2 file:py-1"
              onChange={(e) => setPendingPdf(e.target.files?.[0] ?? null)}
            />
            <p className="mt-1 text-xs text-slate-500">Optional. Saved after the part is created or updated.</p>
          </div>
          {editingPartId != null && (
            <div className="md:col-span-2">
              <label className="text-xs text-slate-500">
                Reason for revision change {originalDrawingRev !== (drawing_rev || null) ? "(required if rev changed)" : ""}
              </label>
              <textarea
                className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
                rows={2}
                value={revisionReason}
                onChange={(e) => setRevisionReason(e.target.value)}
                placeholder="Required when you change drawing revision"
              />
            </div>
          )}
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <button type="submit" className="w-full rounded bg-blue-700 px-4 py-2 text-sm text-white sm:w-auto">
            {editingPartId != null ? "Update part" : "Save part"}
          </button>
          {editingPartId != null && (
            <button
              type="button"
              className="w-full rounded border border-slate-300 px-4 py-2 text-sm sm:w-auto"
              onClick={cancelEdit}
            >
              Cancel
            </button>
          )}
        </div>
      </form>

      <h2 className="mt-8 text-sm font-semibold text-slate-800">Existing parts</h2>
      <p className="text-xs text-slate-500">Type in Part number above to filter; row numbers reflect visible rows only.</p>

      <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200 shadow-sm">
        <table className="min-w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-100 text-slate-700">
              <th className="px-3 py-2 font-semibold">#</th>
              <th className="px-3 py-2 font-semibold">Part number</th>
              <th className="px-3 py-2 font-semibold">Drawing rev</th>
              <th className="px-3 py-2 font-semibold">Description</th>
              <th className="px-3 py-2 font-semibold">Drawing</th>
              <th className="px-3 py-2 font-semibold">JSON</th>
              <th className="px-3 py-2 font-semibold">Action</th>
            </tr>
          </thead>
          <tbody>
            {visibleRows.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-slate-500">
                  {rows.length === 0
                    ? "No parts yet — add one above, import JSON, or upload Excel."
                    : "No parts match the filter."}
                </td>
              </tr>
            ) : (
              visibleRows.map((r, i) => (
                <tr key={r.part_id} className="border-b border-slate-100 hover:bg-slate-50/80">
                  <td className="px-3 py-2 text-slate-500">{i + 1}</td>
                  <td className="px-3 py-2 font-mono font-medium text-blue-800">
                    <Link className="hover:underline" to={`/workspace/parts/${r.part_id}`}>
                      {r.part_no}
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-slate-700">{r.drawing_rev ?? ""}</td>
                  <td className="px-3 py-2 text-slate-700">{r.description ?? ""}</td>
                  <td className="px-3 py-2 text-xs">
                    {r.has_drawing ? (
                      <span className="flex flex-wrap gap-1">
                        <button
                          type="button"
                          className="rounded border border-slate-300 bg-white px-2 py-0.5 text-blue-800 hover:bg-slate-50"
                          onClick={() => void viewDrawing(r.part_id)}
                        >
                          View
                        </button>
                        <button
                          type="button"
                          className="rounded border border-slate-300 bg-white px-2 py-0.5 hover:bg-slate-50"
                          onClick={() => void downloadDrawing(r.part_id, r.part_no)}
                        >
                          PDF
                        </button>
                      </span>
                    ) : (
                      <Link
                        className="text-blue-700 underline hover:text-blue-900"
                        to={`/workspace/parts/${r.part_id}`}
                      >
                        Add PDF
                      </Link>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      className="rounded border border-slate-300 bg-white px-2 py-1 text-xs hover:bg-slate-50"
                      onClick={() => void downloadOne(r.part_id, r.part_no)}
                    >
                      Download
                    </button>
                  </td>
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      className="rounded border border-slate-300 bg-white px-2 py-1 text-xs hover:bg-slate-50"
                      onClick={() => startEdit(r)}
                    >
                      Edit
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {pendingExcelBundle && (
        <PartMasterExcelReview
          bundle={pendingExcelBundle}
          fileLabel={pendingExcelLabel}
          onConfirm={(nextBundle) => void confirmExcelImport(nextBundle)}
          onCancel={cancelExcelReview}
          busy={excelBusy}
        />
      )}
    </div>
  );
}
