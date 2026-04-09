import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  downloadWorkspacePdf,
  openWorkspacePdfInNewTab,
  workspaceDownloadBlob,
  workspaceFetch,
  getWorkspaceCustomerId,
  setWorkspaceCustomerId,
} from "../../api";
import PartMasterExcelReview, { type PartMasterBundle } from "../../components/PartMasterExcelReview";
import { sanitizePartNoUpper as sanitizePartMasterAlnumUpper } from "../../utils/partFields";

type Row = {
  part_id: number;
  part_no: string;
  customer_id: number;
  customer_vendor_code?: string;
  customer_name?: string;
  drawing_rev: string | null;
  description: string | null;
  has_drawing?: boolean;
};

type CustomerOpt = { id: number; vendor_code: string; name: string };

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
  const [deleteBusyId, setDeleteBusyId] = useState<number | null>(null);
  const importRef = useRef<HTMLInputElement>(null);
  const excelRef = useRef<HTMLInputElement>(null);
  const [customers, setCustomers] = useState<CustomerOpt[]>([]);
  /** Table filter: null = all customers */
  const [filterCustomerId, setFilterCustomerId] = useState<number | null>(null);
  /** Part form / import target customer (required when multiple customers) */
  const [formCustomerId, setFormCustomerId] = useState<number | null>(null);

  async function load() {
    const q = filterCustomerId != null ? `?customer_id=${filterCustomerId}` : "";
    setRows(await workspaceFetch<Row[]>(`/api/app/parts${q}`));
  }

  useEffect(() => {
    workspaceFetch<CustomerOpt[]>("/api/app/customers")
      .then((list) => {
        setCustomers(list);
        const ws = getWorkspaceCustomerId();
        if (list.length === 1) {
          setFormCustomerId(list[0].id);
        } else if (ws != null && list.some((c) => c.id === ws)) {
          setFormCustomerId(ws);
        } else if (list.length > 1) {
          setFormCustomerId((prev) => prev ?? list[0].id);
        }
      })
      .catch(() => setCustomers([]));
  }, []);

  useEffect(() => {
    load().catch((e) => setErr(e.message));
  }, [filterCustomerId]);
  useEffect(() => {
    if (formCustomerId != null) {
      setWorkspaceCustomerId(formCustomerId);
    }
  }, [formCustomerId]);


  const formRows = useMemo(
    () => rows.filter((r) => formCustomerId == null || r.customer_id === formCustomerId),
    [rows, formCustomerId],
  );

  const filterQ = sanitizePartMasterAlnumUpper(part_no).toLowerCase();
  const visibleRows = useMemo(() => {
    if (!filterQ) return rows;
    return rows.filter((r) => r.part_no.toLowerCase().includes(filterQ));
  }, [rows, filterQ]);

  /** Exact match: helps avoid duplicate uploads when the part already exists */
  const partNoExistsInMaster = useMemo(() => {
    const q = sanitizePartMasterAlnumUpper(part_no).toLowerCase();
    if (!q) return false;
    return formRows.some((r) => sanitizePartMasterAlnumUpper(r.part_no).toLowerCase() === q);
  }, [formRows, part_no]);

  const existingPartNoKeys = useMemo(() => {
    const s = new Set<string>();
    for (const r of formRows) {
      s.add(sanitizePartMasterAlnumUpper(r.part_no).toLowerCase());
    }
    return s;
  }, [formRows]);

  async function downloadAll() {
    setErr(null);
    setImportMsg(null);
    try {
      const exq = filterCustomerId != null ? `?customer_id=${filterCustomerId}` : "";
      const blob = await workspaceDownloadBlob(`/api/app/parts/export-all${exq}`);
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
      const fd = new FormData();
      fd.append("file", file);
      const bundle = await workspaceFetch<PartMasterBundle>(endpoint, {
        method: "POST",
        body: fd,
      });
      if (!bundle.parts?.length) {
        setErr("Excel parsed but no parts were found — check the Parts sheet and Part Number column.");
        return;
      }
      const dupes: string[] = [];
      const seenDupe = new Set<string>();
      for (const sl of bundle.parts) {
        const raw = (sl.part?.part_no ?? "").trim();
        const key = sanitizePartMasterAlnumUpper(raw).toLowerCase();
        if (key && existingPartNoKeys.has(key) && !seenDupe.has(key)) {
          seenDupe.add(key);
          dupes.push(raw);
        }
      }
      if (dupes.length) {
        const shown = dupes.slice(0, 8);
        const more = dupes.length - shown.length;
        setErr(
          `Part number(s) already in Parts master — remove them from the file or delete the existing part(s) first: ${shown.join(", ")}${more > 0 ? ` (+${more} more)` : ""}`,
        );
        return;
      }
      setPendingExcelLabel(file.name);
      setPendingExcelBundle(bundle);
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
          customer_id: formCustomerId,
        }),
      });
      if (pendingPdf) {
        const fd = new FormData();
        fd.append("file", pendingPdf);
        await workspaceFetch(`/api/app/parts/${r.part_id}/drawing`, {
          method: "POST",
          body: fd,
        });
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
    setFormCustomerId(r.customer_id);
    setOriginalDrawingRev(r.drawing_rev ?? null);
    setPartNo(sanitizePartMasterAlnumUpper(r.part_no));
    setDrawingRev(r.drawing_rev ?? "");
    setDescription(sanitizePartMasterAlnumUpper(r.description ?? ""));
    setRevisionReason("");
    setPendingPdf(null);
    setErr(null);
  }

  function cancelEdit() {
    setEditingPartId(null);
    const ws = getWorkspaceCustomerId();
    if (customers.length === 1) {
      setFormCustomerId(customers[0].id);
    } else if (ws != null && customers.some((c) => c.id === ws)) {
      setFormCustomerId(ws);
    }
    setOriginalDrawingRev(null);
    setPartNo("");
    setDrawingRev("");
    setDescription("");
    setRevisionReason("");
    setPendingPdf(null);
  }

  async function deletePartRow(r: Row) {
    if (
      !window.confirm(
        `Delete part "${r.part_no}" and all Section A–D data for it? This cannot be undone.`,
      )
    ) {
      return;
    }
    setErr(null);
    setImportMsg(null);
    setDeleteBusyId(r.part_id);
    try {
      await workspaceFetch<{ ok: boolean }>(`/api/app/parts/${r.part_id}`, { method: "DELETE" });
      if (editingPartId === r.part_id) {
        cancelEdit();
      }
      setImportMsg(`Deleted part “${r.part_no}”.`);
      await load();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Delete failed");
    } finally {
      setDeleteBusyId(null);
    }
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
      {customers.length > 0 && (
        <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
          <label className="flex flex-wrap items-center gap-2 text-sm text-slate-700">
            <span className="text-slate-600">Show parts for</span>
            <select
              className="rounded border border-slate-300 bg-white px-2 py-1.5 text-sm"
              value={filterCustomerId ?? ""}
              onChange={(e) => {
                const v = e.target.value;
                setFilterCustomerId(v === "" ? null : Number(v));
              }}
            >
              <option value="">All customers</option>
              {customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.vendor_code} — {c.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-wrap items-center gap-2 text-sm text-slate-700">
            <span className="text-slate-600">Add / import for customer</span>
            <select
              className="rounded border border-slate-300 bg-white px-2 py-1.5 text-sm"
              value={formCustomerId ?? ""}
              onChange={(e) => setFormCustomerId(Number(e.target.value))}
              disabled={customers.length <= 1}
            >
              {customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.vendor_code} — {c.name}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
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
            <label className="text-xs text-slate-500">Part number * (also filters table below) — A–Z and 0–9 only</label>
            <div className="mt-1 flex items-center gap-2">
              <input
                className="min-w-0 flex-1 rounded border border-slate-300 px-2 py-1.5 text-sm uppercase"
                value={part_no}
                onChange={(e) => setPartNo(sanitizePartMasterAlnumUpper(e.target.value))}
                inputMode="text"
                autoCapitalize="characters"
                spellCheck={false}
                pattern="[A-Z0-9]+"
                title="Letters A–Z and digits 0–9 only"
                required
                autoComplete="off"
                aria-describedby={partNoExistsInMaster ? "parts-master-part-exists" : undefined}
              />
              {editingPartId == null && partNoExistsInMaster ? (
                <span
                  id="parts-master-part-exists"
                  className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-emerald-600 text-white shadow-sm ring-2 ring-emerald-100"
                  title="This part number is already saved — use the table below to edit or open the part"
                  aria-label="Part number already in Parts master"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 20 20"
                    fill="currentColor"
                    className="h-4 w-4"
                    aria-hidden
                  >
                    <path
                      fillRule="evenodd"
                      d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z"
                      clipRule="evenodd"
                    />
                  </svg>
                </span>
              ) : null}
            </div>
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
            <label className="text-xs text-slate-500">Description — A–Z and 0–9 only (optional)</label>
            <input
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 text-sm uppercase"
              value={description}
              onChange={(e) => setDescription(sanitizePartMasterAlnumUpper(e.target.value))}
              inputMode="text"
              autoCapitalize="characters"
              spellCheck={false}
              pattern="[A-Z0-9]*"
              title="Letters A–Z and digits 0–9 only"
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
              <th className="px-3 py-2 font-semibold">Customer</th>
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
                <td colSpan={8} className="px-3 py-6 text-center text-slate-500">
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
                  <td className="px-3 py-2 text-xs text-slate-600">
                    {r.customer_vendor_code ?? "—"}
                    {r.customer_name ? <span className="text-slate-500"> · {r.customer_name}</span> : null}
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
                    <div className="flex flex-wrap items-center gap-1">
                      <button
                        type="button"
                        className="rounded border border-slate-300 bg-white px-2 py-1 text-xs hover:bg-slate-50"
                        onClick={() => startEdit(r)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="rounded border border-red-300 bg-white px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
                        disabled={deleteBusyId === r.part_id}
                        onClick={() => void deletePartRow(r)}
                      >
                        {deleteBusyId === r.part_id ? "Deleting…" : "Delete"}
                      </button>
                    </div>
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
