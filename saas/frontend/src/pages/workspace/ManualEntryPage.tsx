import { FormEvent, useEffect, useLayoutEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { getWorkspaceCustomerId, setWorkspaceCustomerId, workspaceFetch } from "../../api";
import { sanitizePartNoUpper } from "../../utils/partFields";

type ManualRow = {
  partNumber: string;
  quantity: string;
  invoiceNumber: string;
  date: string;
};

/** Manual invoice entry: one row per FIR line item (aligned with typical Excel batch size). */
const MAX_MANUAL_ROWS = 50;

function partKeyFromInput(s: string): string {
  return sanitizePartNoUpper(s).toLowerCase();
}

type CustomerRow = { id: number; vendor_code: string; name: string };

function blankRow(): ManualRow {
  return { partNumber: "", quantity: "", invoiceNumber: "", date: "" };
}

function rowHasData(r: ManualRow): boolean {
  return !!(r.partNumber.trim() || r.quantity.trim() || r.invoiceNumber.trim() || r.date.trim());
}

function clampRowCount(n: number): number {
  if (!Number.isFinite(n)) return 1;
  return Math.min(MAX_MANUAL_ROWS, Math.max(1, Math.floor(n)));
}

type PartMasterRow = {
  part_id: number;
  part_no: string;
  drawing_rev: string | null;
  description: string | null;
};

function toDateInput(v: string): string {
  const s = (v || "").trim();
  if (!s) return "";
  // accept dd.mm.yyyy / dd-mm-yyyy / dd/mm/yyyy
  const m = s.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/);
  if (m) {
    const dd = m[1].padStart(2, "0");
    const mm = m[2].padStart(2, "0");
    const yyyy = m[3];
    return `${yyyy}-${mm}-${dd}`;
  }
  return s;
}

function fromDateInput(v: string): string {
  const s = (v || "").trim();
  if (!s) return "";
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return s;
  return `${m[3]}.${m[2]}.${m[1]}`;
}

export default function ManualEntryPage() {
  const nav = useNavigate();
  const loc = useLocation();

  const [rows, setRows] = useState<ManualRow[]>([blankRow()]);
  const [rowCountInput, setRowCountInput] = useState("1");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [partMasterKeys, setPartMasterKeys] = useState<Set<string>>(new Set());
  const [customers, setCustomers] = useState<CustomerRow[]>([]);
  const [scopeCustomerId, setScopeCustomerId] = useState<number | null>(null);

  /** Open with N empty rows when coming from upload (or other) with `desiredRowCount`. */
  useLayoutEffect(() => {
    const raw = (loc.state as { desiredRowCount?: number } | null)?.desiredRowCount;
    if (raw == null || !Number.isFinite(raw)) return;
    const c = clampRowCount(raw);
    setRows(Array.from({ length: c }, () => blankRow()));
    setRowCountInput(String(c));
  }, [loc.key]);

  useEffect(() => {
    workspaceFetch<CustomerRow[]>("/api/app/customers")
      .then((list) => {
        setCustomers(list);
        const ws = getWorkspaceCustomerId();
        if (list.length === 1) {
          setScopeCustomerId(list[0].id);
          setWorkspaceCustomerId(list[0].id);
        } else if (ws != null && list.some((c) => c.id === ws)) {
          setScopeCustomerId(ws);
        } else if (list.length > 1) {
          const pick = ws != null && list.some((c) => c.id === ws) ? ws : list[0].id;
          setScopeCustomerId(pick);
          setWorkspaceCustomerId(pick);
        }
      })
      .catch(() => setCustomers([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (scopeCustomerId == null) {
      setPartMasterKeys(new Set());
      return;
    }
    setWorkspaceCustomerId(scopeCustomerId);
    const q = `?customer_id=${scopeCustomerId}`;
    workspaceFetch<PartMasterRow[]>(`/api/app/parts${q}`)
      .then((parts) => {
        if (cancelled) return;
        setPartMasterKeys(new Set(parts.map((p) => sanitizePartNoUpper(p.part_no).toLowerCase())));
      })
      .catch(() => {
        if (!cancelled) setPartMasterKeys(new Set());
      });
    return () => {
      cancelled = true;
    };
  }, [scopeCustomerId]);

  const canAddMore = rows.length < MAX_MANUAL_ROWS;

  function updateRow(i: number, patch: Partial<ManualRow>) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }

  function applyRowCountFromInput() {
    const parsed = parseInt(rowCountInput, 10);
    const n = clampRowCount(Number.isFinite(parsed) ? parsed : rows.length);

    if (n === rows.length) {
      setRowCountInput(String(n));
      return;
    }

    if (n < rows.length) {
      const removed = rows.slice(n);
      if (
        removed.some(rowHasData) &&
        !window.confirm("Remove rows that already have values? Those values will be lost.")
      ) {
        return;
      }
      setRows(rows.slice(0, n));
      setRowCountInput(String(n));
      return;
    }

    setRows((prev) => [...prev, ...Array.from({ length: n - prev.length }, () => blankRow())]);
    setRowCountInput(String(n));
  }

  function addRow() {
    if (!canAddMore) return;
    setRows((prev) => {
      const next = [...prev, blankRow()];
      setRowCountInput(String(next.length));
      return next;
    });
  }

  function removeRow(i: number) {
    setRows((prev) => {
      if (prev.length <= 1) return prev;
      const next = prev.filter((_, idx) => idx !== i);
      setRowCountInput(String(next.length));
      return next;
    });
  }

  const sanitized = useMemo(() => {
    return rows
      .map((r) => ({
        "Part Number": sanitizePartNoUpper(r.partNumber),
        Quantity: r.quantity.trim(),
        "Invoice Number": r.invoiceNumber.trim(),
        Date: fromDateInput(r.date),
      }))
      .filter((r) => Object.values(r).some((v) => String(v).trim() !== ""));
  }, [rows]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    if (!sanitized.length) {
      setErr("Enter at least one part row.");
      return;
    }
    for (let i = 0; i < sanitized.length; i++) {
      const r = sanitized[i];
      if (!r["Part Number"]) {
        setErr(`Row ${i + 1}: Part Number is required.`);
        return;
      }
      if (!r.Quantity) {
        setErr(`Row ${i + 1}: Quantity is required.`);
        return;
      }
      if (!r["Invoice Number"]) {
        setErr(`Row ${i + 1}: Invoice Number is required.`);
        return;
      }
      if (!r.Date) {
        setErr(`Row ${i + 1}: Date is required.`);
        return;
      }
    }
    const invoiceSeen = new Set<string>();
    for (let i = 0; i < sanitized.length; i++) {
      const inv = sanitized[i]["Invoice Number"].trim().toLowerCase();
      if (invoiceSeen.has(inv)) {
        setErr(`Invoice Number must be unique. Duplicate found at row ${i + 1}.`);
        return;
      }
      invoiceSeen.add(inv);
    }

    setBusy(true);
    try {
      const pre = await workspaceFetch<{ ok: boolean; reason?: string }>("/api/app/upload-check");
      if (!pre.ok && pre.reason === "select_customer") {
        nav("/workspace/select-customer");
        return;
      }
      if (!pre.ok && pre.reason === "no_customers") {
        throw new Error("Add at least one customer before creating FIR manually.");
      }
      if (scopeCustomerId == null) {
        throw new Error("Select a customer for this FIR.");
      }
      const parts = await workspaceFetch<PartMasterRow[]>(`/api/app/parts?customer_id=${scopeCustomerId}`);
      const partMap = new Map(parts.map((p) => [sanitizePartNoUpper(p.part_no).toLowerCase(), p]));
      const missing: string[] = [];
      const enrichedRows = sanitized.map((r) => {
        const key = sanitizePartNoUpper(r["Part Number"]).toLowerCase();
        const part = partMap.get(key);
        if (!part) {
          missing.push(r["Part Number"]);
          return r;
        }
        const description = (part.description ?? "").trim();
        const drawRev = (part.drawing_rev ?? "").trim();
        return {
          ...r,
          Description: description,
          "Draw Rev": drawRev,
          draw_rev: drawRev,
        };
      });
      if (missing.length) {
        const uniq = Array.from(new Set(missing));
        throw new Error(
          `Part Number not found in Parts master: ${uniq.join(", ")}. Add these in Parts master first.`,
        );
      }
      nav("/workspace/extracted", {
        state: {
          rows: enrichedRows,
          columns: ["Part Number", "Description", "Draw Rev", "Quantity", "Invoice Number", "Date"],
          filename: "Manual entry",
        },
      });
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to continue");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h1 className="text-xl font-semibold">Manual FIR entry (no Excel)</h1>
      <p className="mt-1 text-sm text-slate-600">
        One table row per FIR report. Up to {MAX_MANUAL_ROWS} rows. Set the count and click Apply, or add rows one at a
        time.
      </p>
      {customers.length > 1 && (
        <div className="mt-4 rounded border border-slate-200 bg-slate-50 px-3 py-2">
          <label className="flex flex-wrap items-center gap-2 text-sm text-slate-800">
            <span className="font-medium">Customer for this FIR</span>
            <select
              className="rounded border border-slate-300 bg-white px-2 py-1.5 text-sm"
              value={scopeCustomerId ?? ""}
              onChange={(e) => setScopeCustomerId(Number(e.target.value))}
            >
              {customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.vendor_code} — {c.name}
                </option>
              ))}
            </select>
          </label>
          <p className="mt-1 text-xs text-slate-500">Parts master is matched for this customer only.</p>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-end gap-2">
        <label className="text-sm text-slate-700">
          <span className="block text-slate-600">Number of reports (rows)</span>
          <input
            type="number"
            min={1}
            max={MAX_MANUAL_ROWS}
            className="mt-1 w-28 rounded border border-slate-300 bg-white px-2 py-1.5 tabular-nums"
            value={rowCountInput}
            onChange={(e) => setRowCountInput(e.target.value)}
          />
        </label>
        <button
          type="button"
          className="rounded border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50"
          onClick={applyRowCountFromInput}
        >
          Apply
        </button>
        <button
          type="button"
          className="rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 hover:bg-slate-50 disabled:opacity-50"
          onClick={addRow}
          disabled={!canAddMore}
        >
          Add one row
        </button>
      </div>

      <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200">
        <table className="min-w-full border-collapse text-sm">
          <thead>
            <tr className="bg-slate-100 text-left text-slate-900">
              <th className="border-b border-slate-200 px-2 py-2 font-semibold">#</th>
              <th className="border-b border-slate-200 px-2 py-2 font-semibold">Part number</th>
              <th className="border-b border-slate-200 px-2 py-2 font-semibold">Qty</th>
              <th className="border-b border-slate-200 px-2 py-2 font-semibold">Invoice #</th>
              <th className="border-b border-slate-200 px-2 py-2 font-semibold">Date</th>
              <th className="border-b border-slate-200 px-2 py-2 font-semibold w-20" aria-label="Remove row" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className={i % 2 === 0 ? "bg-white" : "bg-slate-50/80"}>
                <td className="border-b border-slate-100 px-2 py-1.5 align-middle text-slate-500 tabular-nums">
                  {i + 1}
                </td>
                <td className="border-b border-slate-100 px-2 py-1.5 align-middle">
                  <div className="flex min-w-[10rem] items-center gap-1">
                    <input
                      className="w-full min-w-0 rounded border border-slate-300 px-2 py-1.5 uppercase"
                      value={r.partNumber}
                      onChange={(e) => updateRow(i, { partNumber: sanitizePartNoUpper(e.target.value) })}
                      autoComplete="off"
                      inputMode="text"
                      autoCapitalize="characters"
                      spellCheck={false}
                      pattern="[A-Z0-9]*"
                      title="Letters A–Z and digits 0–9 only"
                      aria-describedby={partMasterKeys.has(partKeyFromInput(r.partNumber)) ? `part-in-master-${i}` : undefined}
                    />
                    {sanitizePartNoUpper(r.partNumber) && partMasterKeys.has(partKeyFromInput(r.partNumber)) ? (
                      <span
                        id={`part-in-master-${i}`}
                        className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-600 text-white shadow-sm ring-2 ring-emerald-100"
                        title="This part number is in Parts master"
                        aria-label="Part number found in Parts master"
                      >
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          viewBox="0 0 20 20"
                          fill="currentColor"
                          className="h-3.5 w-3.5"
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
                </td>
                <td className="border-b border-slate-100 px-2 py-1.5 align-middle">
                  <input
                    className="w-full min-w-[4rem] rounded border border-slate-300 px-2 py-1.5"
                    value={r.quantity}
                    onChange={(e) => updateRow(i, { quantity: e.target.value })}
                  />
                </td>
                <td className="border-b border-slate-100 px-2 py-1.5 align-middle">
                  <input
                    className="w-full min-w-[6rem] rounded border border-slate-300 px-2 py-1.5"
                    value={r.invoiceNumber}
                    onChange={(e) => updateRow(i, { invoiceNumber: e.target.value })}
                  />
                </td>
                <td className="border-b border-slate-100 px-2 py-1.5 align-middle">
                  <input
                    type="date"
                    className="w-full min-w-[9rem] rounded border border-slate-300 px-2 py-1.5"
                    value={toDateInput(r.date)}
                    onChange={(e) => updateRow(i, { date: e.target.value })}
                  />
                </td>
                <td className="border-b border-slate-100 px-2 py-1.5 align-middle text-center">
                  {rows.length > 1 ? (
                    <button
                      type="button"
                      className="text-xs text-red-700 underline hover:text-red-800"
                      onClick={() => removeRow(i)}
                    >
                      Remove
                    </button>
                  ) : (
                    <span className="text-slate-300">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button
          type="submit"
          className="rounded bg-blue-700 px-4 py-2 text-sm font-medium text-white hover:bg-blue-800 disabled:opacity-60"
          disabled={busy}
        >
          {busy ? "Continuing…" : "Continue to inspection"}
        </button>
      </div>
      {err && <p className="mt-3 text-sm text-red-600">{err}</p>}
    </form>
  );
}
