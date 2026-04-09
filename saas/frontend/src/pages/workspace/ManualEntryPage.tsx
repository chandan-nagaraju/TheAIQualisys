import { FormEvent, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getWorkspaceCustomerId, setWorkspaceCustomerId, workspaceFetch } from "../../api";
import { sanitizePartNoUpper } from "../../utils/partFields";

type ManualRow = {
  partNumber: string;
  quantity: string;
  invoiceNumber: string;
  date: string;
};

const MAX_ROWS = 3;

function partKeyFromInput(s: string): string {
  return sanitizePartNoUpper(s).toLowerCase();
}

type CustomerRow = { id: number; vendor_code: string; name: string };

function blankRow(): ManualRow {
  return { partNumber: "", quantity: "", invoiceNumber: "", date: "" };
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
  const [rows, setRows] = useState<ManualRow[]>([blankRow()]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [partMasterKeys, setPartMasterKeys] = useState<Set<string>>(new Set());
  const [customers, setCustomers] = useState<CustomerRow[]>([]);
  const [scopeCustomerId, setScopeCustomerId] = useState<number | null>(null);

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

  const canAddMore = rows.length < MAX_ROWS;

  function updateRow(i: number, patch: Partial<ManualRow>) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }

  function addRow() {
    if (!canAddMore) return;
    setRows((prev) => [...prev, blankRow()]);
  }

  function removeRow(i: number) {
    setRows((prev) => prev.filter((_, idx) => idx !== i));
  }

  const sanitized = useMemo(() => {
    return rows
      .map((r) => ({
        "Part Number": sanitizePartNoUpper(r.partNumber),
        Quantity: r.quantity.trim(),
        "Invoice Number": r.invoiceNumber.trim(),
        Date: fromDateInput(r.date),
      }))
      .filter((r) =>
        Object.values(r).some((v) => String(v).trim() !== ""),
      );
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
        throw new Error('Select a customer for this FIR.');
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
        Add up to {MAX_ROWS} parts and continue to inspection/results to generate and download FIR reports.
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

      <div className="mt-4 space-y-3">
        {rows.map((r, i) => (
          <div key={i} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-sm font-medium text-slate-800">Part row {i + 1}</p>
              {rows.length > 1 && (
                <button
                  type="button"
                  className="text-xs text-red-700 underline"
                  onClick={() => removeRow(i)}
                >
                  Remove
                </button>
              )}
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="text-sm">
                <span className="block text-slate-600">Part Number (A–Z, 0–9 only)</span>
                <div className="mt-1 flex items-center gap-2">
                  <input
                    className="min-w-0 flex-1 rounded border border-slate-300 px-3 py-2 uppercase"
                    value={r.partNumber}
                    onChange={(e) => updateRow(i, { partNumber: sanitizePartNoUpper(e.target.value) })}
                    autoComplete="off"
                    inputMode="text"
                    autoCapitalize="characters"
                    spellCheck={false}
                    pattern="[A-Z0-9]+"
                    title="Letters A–Z and digits 0–9 only"
                    aria-describedby={partMasterKeys.has(partKeyFromInput(r.partNumber)) ? `part-in-master-${i}` : undefined}
                  />
                  {sanitizePartNoUpper(r.partNumber) &&
                  partMasterKeys.has(partKeyFromInput(r.partNumber)) ? (
                    <span
                      id={`part-in-master-${i}`}
                      className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-emerald-600 text-white shadow-sm ring-2 ring-emerald-100"
                      title="This part number is in Parts master"
                      aria-label="Part number found in Parts master"
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
              </label>
              <label className="text-sm">
                <span className="block text-slate-600">Quantity</span>
                <input
                  className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
                  value={r.quantity}
                  onChange={(e) => updateRow(i, { quantity: e.target.value })}
                />
              </label>
              <label className="text-sm">
                <span className="block text-slate-600">Invoice Number</span>
                <input
                  className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
                  value={r.invoiceNumber}
                  onChange={(e) => updateRow(i, { invoiceNumber: e.target.value })}
                />
              </label>
              <label className="text-sm sm:col-span-2">
                <span className="block text-slate-600">Date</span>
                <input
                  type="date"
                  className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
                  value={toDateInput(r.date)}
                  onChange={(e) => updateRow(i, { date: e.target.value })}
                />
              </label>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 hover:bg-slate-50 disabled:opacity-50"
          onClick={addRow}
          disabled={!canAddMore}
        >
          Add part row
        </button>
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
