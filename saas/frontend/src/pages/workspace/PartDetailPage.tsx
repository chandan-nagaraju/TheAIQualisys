import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  downloadWorkspacePdf,
  openWorkspacePdfInNewTab,
  workspaceDownloadBlob,
  workspaceFetch,
  workspacePostFile,
} from "../../api";

type Spec = {
  id?: number;
  parameter: string;
  specification: string;
  special_char: string;
  method_of_inspection: string;
};

type RevRow = {
  id: number;
  previous_rev: string | null;
  new_rev: string | null;
  reason: string;
  changed_by_user_id: number | null;
  created_at: string | null;
};

type Detail = {
  part_id: number;
  part_no: string;
  drawing_rev: string | null;
  description: string | null;
  drawing_pdf_filename?: string | null;
  drawing_file_present?: boolean;
  revision_rows?: RevRow[];
  spec_rows: Spec[];
  ccp_rows: Spec[];
  material_rows: { material_grade: string }[];
  coating_rows: Spec[];
};

function emptySpec(): Spec {
  return { parameter: "", specification: "", special_char: "", method_of_inspection: "" };
}

function isSpecRowEmpty(r: Spec): boolean {
  return (
    !r.parameter.trim() && !r.specification.trim() && !r.special_char.trim() && !r.method_of_inspection.trim()
  );
}

/** Same as legacy: tab-separated lines → Parameter, Specification, Special char, Method. Appends to table, or replaces a single empty starter row. */
function mergePasteFourColumn(current: Spec[], text: string): Spec[] {
  const raw = text.trim();
  if (!raw) return current;
  const lines = raw.split(/\r?\n/).filter((l) => l.trim());
  const parsed: Spec[] = lines.map((line) => {
    const cells = line.split("\t").map((c) => c.trim());
    return {
      parameter: cells[0] ?? "",
      specification: cells[1] ?? "",
      special_char: cells[2] ?? "",
      method_of_inspection: cells[3] ?? "",
    };
  });
  const onlyEmpty = current.length === 1 && isSpecRowEmpty(current[0]);
  if (onlyEmpty) return parsed.length ? parsed : [emptySpec()];
  return [...current, ...parsed];
}

function looksLikeCoatingInspectionMethod(x: string): boolean {
  const t = x.trim();
  if (!t) return false;
  const u = t.toUpperCase();
  if (u === "VISUAL" || u.startsWith("VISUAL ")) return true;
  return /^(DVC|DHG|DHI|RG|R\.G\.?|MM|CMM|UT|MPI|DFT|DFT\s*METER)$/i.test(t);
}

/** One pasted line for Section D: tolerate 3 Excel columns (Parameter, Specification, Method) and single-cell colour+process text. */
function parseCoatingPasteLine(line: string): Spec {
  const cells = line.split("\t").map((c) => c.trim());
  if (cells.length >= 4) {
    return {
      parameter: cells[0] ?? "",
      specification: cells[1] ?? "",
      special_char: cells[2] ?? "",
      method_of_inspection: cells[3] ?? "",
    };
  }
  if (cells.length === 3) {
    return {
      parameter: cells[0] ?? "",
      specification: cells[1] ?? "",
      special_char: "",
      method_of_inspection: cells[2] ?? "",
    };
  }
  if (cells.length === 2) {
    const a = cells[0] ?? "";
    const b = cells[1] ?? "";
    if (looksLikeCoatingInspectionMethod(b)) {
      return { parameter: a, specification: "", special_char: "", method_of_inspection: b };
    }
    return { parameter: a, specification: b, special_char: "", method_of_inspection: "" };
  }
  const s = cells[0] ?? "";
  const multi = s
    .split(/\s{2,}/)
    .map((x) => x.trim())
    .filter(Boolean);
  if (multi.length >= 2 && looksLikeCoatingInspectionMethod(multi[multi.length - 1]!)) {
    return {
      parameter: multi[0]!,
      specification: multi.slice(1, -1).join(" ").trim(),
      special_char: "",
      method_of_inspection: multi[multi.length - 1]!,
    };
  }
  if (multi.length === 2) {
    return { parameter: multi[0]!, specification: multi[1]!, special_char: "", method_of_inspection: "" };
  }
  const trimmed = s.trim();
  const colorLeading =
    /^(\b(?:black|white|red|blue|green|grey|gray|yellow|orange|brown|zinc|matt|matte|glossy|silver|gold|navy|beige|tan)\b)\s+(.+)$/i.exec(
      trimmed,
    );
  if (colorLeading) {
    return {
      parameter: colorLeading[2]!.trim(),
      specification: colorLeading[1]!.toUpperCase(),
      special_char: "",
      method_of_inspection: "VISUAL",
    };
  }
  return { parameter: trimmed, specification: "", special_char: "", method_of_inspection: "" };
}

function mergePasteCoatingRows(current: Spec[], text: string): Spec[] {
  const raw = text.trim();
  if (!raw) return current;
  const lines = raw.split(/\r?\n/).filter((l) => l.trim());
  const parsed: Spec[] = lines.map((line) => parseCoatingPasteLine(line));
  const onlyEmpty = current.length === 1 && isSpecRowEmpty(current[0]!);
  if (onlyEmpty) return parsed.length ? parsed : [emptySpec()];
  return [...current, ...parsed];
}

/** Legacy C) material: one grade per line (first column if tab-separated). */
function mergePasteMaterialGrades(current: string[], text: string): string[] {
  const raw = text.trim();
  if (!raw) return current;
  const lines = raw.split(/\r?\n/).filter((l) => l.trim());
  const parsed = lines.map((line) => (line.split("\t")[0] ?? "").trim()).filter(Boolean);
  const onlyEmpty = current.length === 1 && !current[0].trim();
  if (onlyEmpty) return parsed.length ? parsed : [""];
  return [...current, ...parsed];
}

function SpecSectionWithPaste({
  title,
  hint,
  pasteLabel,
  placeholder,
  rows,
  setRows,
  onSave,
  mergePaste,
}: {
  title: string;
  hint: string;
  pasteLabel: string;
  placeholder: string;
  rows: Spec[];
  setRows: (r: Spec[]) => void;
  onSave: () => void | Promise<void>;
  /** Override default 4-column paste (e.g. Section D coating heuristics). */
  mergePaste?: (current: Spec[], text: string) => Spec[];
}) {
  const [paste, setPaste] = useState("");

  function fillFromPaste() {
    const merge = mergePaste ?? mergePasteFourColumn;
    setRows(merge(rows, paste));
    setPaste("");
  }

  return (
    <section className="mb-10">
      <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
      <p className="mt-1 text-sm text-slate-600">{hint}</p>
      <div className="mt-3">
        <label className="block text-xs font-medium text-slate-700">{pasteLabel}</label>
        <textarea
          className="mt-1 w-full rounded border border-slate-300 px-2 py-2 font-mono text-sm text-slate-900"
          rows={4}
          value={paste}
          onChange={(e) => setPaste(e.target.value)}
          placeholder={placeholder}
          spellCheck={false}
        />
        <button
          type="button"
          className="mt-2 w-full rounded border border-blue-300 bg-slate-50 px-3 py-2 text-sm font-medium text-blue-800 hover:bg-blue-50 sm:w-auto"
          onClick={fillFromPaste}
        >
          Fill table from paste
        </button>
      </div>
      <div className="mt-4 overflow-x-auto">
        <table className="min-w-full border-collapse text-sm">
          <thead>
            <tr className="bg-slate-100">
              <th className="border border-slate-200 px-2 py-1.5 text-left">Parameter</th>
              <th className="border border-slate-200 px-2 py-1.5 text-left">Specification</th>
              <th className="border border-slate-200 px-2 py-1.5 text-left">Special char</th>
              <th className="border border-slate-200 px-2 py-1.5 text-left">Method</th>
              <th className="border border-slate-200 px-2 py-1.5 w-10" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                {(["parameter", "specification", "special_char", "method_of_inspection"] as const).map((k) => (
                  <td key={k} className="border border-slate-200 p-0">
                    <input
                      className="w-full min-w-[6rem] px-2 py-1.5 text-slate-900"
                      value={r[k]}
                      onChange={(e) => {
                        const n = [...rows];
                        n[i] = { ...n[i], [k]: e.target.value };
                        setRows(n);
                      }}
                    />
                  </td>
                ))}
                <td className="border border-slate-200 px-1 text-center">
                  <button type="button" className="text-lg leading-none text-red-600 hover:text-red-800" title="Delete row" onClick={() => setRows(rows.filter((_, j) => j !== i))}>
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button type="button" className="mt-2 text-sm text-blue-700 underline" onClick={() => setRows([...rows, emptySpec()])}>
        Add row
      </button>
      <button type="button" className="ml-4 mt-2 rounded bg-blue-700 px-3 py-1.5 text-sm text-white hover:bg-blue-800" onClick={() => void onSave()}>
        Save section
      </button>
    </section>
  );
}

function MaterialSectionWithPaste({
  rows,
  setRows,
  onSave,
}: {
  rows: string[];
  setRows: (r: string[]) => void;
  onSave: () => void | Promise<void>;
}) {
  const [paste, setPaste] = useState("");

  function fillFromPaste() {
    setRows(mergePasteMaterialGrades(rows, paste));
    setPaste("");
  }

  return (
    <section className="mb-10">
      <h2 className="text-lg font-semibold text-slate-900">C) Material grade</h2>
      <p className="mt-1 text-sm text-slate-600">
        Paste one material grade per line (or from Excel — first column per line). Add rows or edit, then save.
      </p>
      <div className="mt-3">
        <label className="block text-xs font-medium text-slate-700">Paste from Excel (one grade per line):</label>
        <textarea
          className="mt-1 w-full max-w-2xl rounded border border-slate-300 px-2 py-2 font-mono text-sm text-slate-900"
          rows={3}
          value={paste}
          onChange={(e) => setPaste(e.target.value)}
          spellCheck={false}
        />
        <button
          type="button"
          className="mt-2 block w-full rounded border border-blue-300 bg-slate-50 px-3 py-2 text-sm font-medium text-blue-800 hover:bg-blue-50 sm:w-auto"
          onClick={fillFromPaste}
        >
          Fill table from paste
        </button>
      </div>
      <div className="mt-4 space-y-2">
        {rows.map((g, i) => (
          <input
            key={i}
            className="block w-full max-w-md rounded border border-slate-300 px-2 py-1.5 text-sm text-slate-900"
            value={g}
            onChange={(e) => {
              const n = [...rows];
              n[i] = e.target.value;
              setRows(n);
            }}
          />
        ))}
      </div>
      <button type="button" className="mt-2 text-sm text-blue-700 underline" onClick={() => setRows([...rows, ""])}>
        Add grade
      </button>
      <button type="button" className="ml-4 mt-2 rounded bg-blue-700 px-3 py-1.5 text-sm text-white hover:bg-blue-800" onClick={() => void onSave()}>
        Save materials
      </button>
    </section>
  );
}

export default function PartDetailPage() {
  const { id } = useParams();
  const [d, setD] = useState<Detail | null>(null);
  const [specs, setSpecs] = useState<Spec[]>([]);
  const [ccps, setCcps] = useState<Spec[]>([]);
  const [mats, setMats] = useState<string[]>([]);
  const [coats, setCoats] = useState<Spec[]>([]);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [actionErr, setActionErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [drawingBusy, setDrawingBusy] = useState(false);

  useEffect(() => {
    if (!id) return;
    workspaceFetch<Detail>(`/api/app/parts/${id}`)
      .then((x) => {
        setD(x);
        setSpecs(x.spec_rows.length ? x.spec_rows : [emptySpec()]);
        setCcps(x.ccp_rows.length ? x.ccp_rows : [emptySpec()]);
        setMats(x.material_rows.length ? x.material_rows.map((m) => m.material_grade) : [""]);
        setCoats(x.coating_rows.length ? x.coating_rows : [emptySpec()]);
      })
      .catch((e) => setLoadErr(e.message));
  }, [id]);

  async function saveSpecs() {
    if (!id) return;
    setMsg(null);
    await workspaceFetch(`/api/app/parts/${id}/specs`, {
      method: "PUT",
      body: JSON.stringify({ rows: specs.filter((r) => r.parameter.trim()) }),
    });
    setMsg("Dimension parameters saved.");
  }

  async function saveCcp() {
    if (!id) return;
    await workspaceFetch(`/api/app/parts/${id}/complaints`, {
      method: "PUT",
      body: JSON.stringify({ rows: ccps.filter((r) => r.parameter.trim()) }),
    });
    setMsg("Complaint parameters saved.");
  }

  async function saveMat() {
    if (!id) return;
    await workspaceFetch(`/api/app/parts/${id}/materials`, {
      method: "PUT",
      body: JSON.stringify({ grades: mats.filter((g) => g.trim()) }),
    });
    setMsg("Material grades saved.");
  }

  async function saveCoat() {
    if (!id) return;
    await workspaceFetch(`/api/app/parts/${id}/coatings`, {
      method: "PUT",
      body: JSON.stringify({ rows: coats.filter((r) => r.parameter.trim()) }),
    });
    setMsg("Coating parameters saved.");
  }

  async function reloadDetail() {
    if (!id) return;
    const x = await workspaceFetch<Detail>(`/api/app/parts/${id}`);
    setD(x);
    setSpecs(x.spec_rows.length ? x.spec_rows : [emptySpec()]);
    setCcps(x.ccp_rows.length ? x.ccp_rows : [emptySpec()]);
    setMats(x.material_rows.length ? x.material_rows.map((m) => m.material_grade) : [""]);
    setCoats(x.coating_rows.length ? x.coating_rows : [emptySpec()]);
  }

  async function uploadDrawing(file: File | undefined) {
    if (!id || !file) return;
    setActionErr(null);
    setMsg(null);
    setDrawingBusy(true);
    try {
      await workspacePostFile(`/api/app/parts/${id}/drawing`, file, "file");
      setMsg("Drawing PDF saved.");
      await reloadDetail();
    } catch (e) {
      setActionErr(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setDrawingBusy(false);
    }
  }

  async function viewDrawingInline() {
    if (!id) return;
    setActionErr(null);
    try {
      openWorkspacePdfInNewTab(`/api/app/parts/${id}/drawing`);
    } catch (e) {
      setActionErr(
        e instanceof Error
          ? `${e.message} Upload a PDF below if needed — inspection and part data are not blocked.`
          : "View failed. Upload a PDF below.",
      );
      await reloadDetail();
    }
  }

  async function downloadDrawingFile() {
    if (!id || !d) return;
    setActionErr(null);
    try {
      const safe = d.part_no.replace(/[^\w.\-]+/g, "_").slice(0, 120) || "part";
      downloadWorkspacePdf(`/api/app/parts/${id}/drawing?download=true`, `${safe}_drawing.pdf`);
    } catch (e) {
      setActionErr(
        e instanceof Error
          ? `${e.message} Add a drawing using the upload field below.`
          : "Download failed. Upload a PDF below.",
      );
      await reloadDetail();
    }
  }

  async function downloadMasterJson() {
    if (!id || !d) return;
    setActionErr(null);
    setMsg(null);
    try {
      const blob = await workspaceDownloadBlob(`/api/app/parts/${id}/export`);
      const safe = d.part_no.replace(/[^\w.\-]+/g, "_").slice(0, 120) || "part";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `fir_part_master_${safe}.json`;
      a.click();
      URL.revokeObjectURL(url);
      setMsg("Part master JSON download started (same format as legacy export).");
    } catch (e) {
      setActionErr(e instanceof Error ? e.message : "Download failed");
    }
  }

  if (loadErr) {
    return <p className="text-red-600">{loadErr}</p>;
  }
  if (!d) {
    return <p className="text-slate-600">Loading…</p>;
  }

  const pastePlaceholderA = "HOLE DIA\tØ 8.5 + 0.20\t\tDVC\nPITCH\t38 ± 0.25\t\tDHG";

  const showDrawingActions = d.drawing_file_present ?? Boolean(d.drawing_pdf_filename);

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <Link className="text-sm text-blue-700 underline" to="/workspace/parts">
        ← Parts list
      </Link>
      <h1 className="mt-4 text-xl font-semibold text-slate-900">Part: {d.part_no}</h1>
      <p className="text-sm text-slate-600">
        Rev: {d.drawing_rev || "—"} · {d.description || "—"}
      </p>
      <p className="mt-2">
        <button
          type="button"
          className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-800 hover:bg-slate-50"
          onClick={() => void downloadMasterJson()}
        >
          Download part master (JSON)
        </button>
        <span className="ml-2 text-xs text-slate-500">Backup or move to another tenant via Parts master → Import.</span>
      </p>

      <div className="mt-6 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-900">Drawing PDF</h2>
        <p className="mt-1 text-xs text-slate-600">
          One PDF per part. Upload replaces the previous file. If the file is missing on the server, you can attach a new
          PDF here — the rest of this page and FIR workflows keep working.
        </p>
        {!showDrawingActions && (
          <p className="mt-2 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            No drawing PDF on file. Choose a PDF below to add one — other part data and FIR steps are unaffected.
          </p>
        )}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input
            type="file"
            accept="application/pdf,.pdf"
            disabled={drawingBusy}
            className="text-sm text-slate-800 file:mr-2 file:rounded file:border file:border-slate-300 file:bg-white file:px-2 file:py-1"
            onChange={(e) => void uploadDrawing(e.target.files?.[0])}
          />
          {showDrawingActions && (
            <>
              <button
                type="button"
                className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm text-blue-800 hover:bg-slate-50"
                onClick={() => void viewDrawingInline()}
              >
                View PDF
              </button>
              <button
                type="button"
                className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-800 hover:bg-slate-50"
                onClick={() => void downloadDrawingFile()}
              >
                Download PDF
              </button>
            </>
          )}
        </div>
      </div>

      {d.revision_rows && d.revision_rows.length > 0 && (
        <div className="mt-6">
          <h2 className="text-sm font-semibold text-slate-900">Drawing revision history</h2>
          <div className="mt-2 overflow-x-auto rounded-lg border border-slate-200">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-slate-100 text-slate-700">
                <tr>
                  <th className="px-3 py-2">From</th>
                  <th className="px-3 py-2">To</th>
                  <th className="px-3 py-2">Reason</th>
                  <th className="px-3 py-2">When</th>
                </tr>
              </thead>
              <tbody>
                {d.revision_rows.map((r) => (
                  <tr key={r.id} className="border-t border-slate-100">
                    <td className="px-3 py-2 font-mono text-xs">{r.previous_rev ?? "—"}</td>
                    <td className="px-3 py-2 font-mono text-xs">{r.new_rev ?? "—"}</td>
                    <td className="px-3 py-2 text-slate-700">{r.reason}</td>
                    <td className="px-3 py-2 text-xs text-slate-500">{r.created_at ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {actionErr && <p className="mt-2 text-sm text-red-600">{actionErr}</p>}
      {msg && <p className="mt-2 text-sm text-green-700">{msg}</p>}

      <SpecSectionWithPaste
        title="A) Dimension parameters (part_spec_data)"
        hint="Paste from Excel (tab-separated: Parameter, Specification, Special char, Method) or add a row, then edit and save. This data is loaded into the FIR report when you generate it."
        pasteLabel="Paste from Excel (columns: Parameter, Specification, Special char, Method — tab-separated, one row per line):"
        placeholder={pastePlaceholderA}
        rows={specs}
        setRows={setSpecs}
        onSave={saveSpecs}
      />

      <SpecSectionWithPaste
        title="B) Customer complaint parameters"
        hint="Paste from Excel (tab-separated) or add a row, edit and save. Loaded into the FIR when you generate the report."
        pasteLabel="Paste from Excel (tab-separated: Parameter, Specification, Special char, Method):"
        placeholder={pastePlaceholderA}
        rows={ccps}
        setRows={setCcps}
        onSave={saveCcp}
      />

      <MaterialSectionWithPaste rows={mats} setRows={setMats} onSave={saveMat} />

      <SpecSectionWithPaste
        title="D) Surface coating"
        hint="Paste from Excel (tab-separated) or add a row, edit and save. Three columns from Excel (Parameter, Specification, Method) map correctly; a single cell like “Black Powder Coating” splits into Specification BLACK, Method VISUAL."
        pasteLabel="Paste from Excel (tab-separated: Parameter, Specification, Special char, Method — or 3 columns: Parameter, Specification, Method):"
        placeholder={pastePlaceholderA}
        rows={coats}
        setRows={setCoats}
        onSave={saveCoat}
        mergePaste={mergePasteCoatingRows}
      />
    </div>
  );
}
