import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiFetch } from "../api";

type Company = {
  id: number;
  company_name: string;
  vendor_code: string;
  trial_start_date: string;
  trial_end_date: string;
  subscription_start: string | null;
  subscription_end: string | null;
  plan_type: string;
  subscription_status: string;
};

type FirIntelMonthRow = {
  year: number;
  month: number;
  row_count: number;
  label: string;
};

/** Indian FY: April (calendarYear) through March (calendarYear + 1). */
function fyAprilStartFromCalendarMonth(calendarYear: number, calendarMonth: number): number {
  return calendarMonth >= 4 ? calendarYear : calendarYear - 1;
}

function formatFyRangeLabel(fyStart: number): string {
  return `${fyStart}-${fyStart + 1}`;
}

type FirIntel = {
  as_of: string;
  company_id: number;
  view?: {
    scope?: "calendar_month" | "financial_year";
    year: number;
    month: number | null;
    month_start: string;
    month_end: string;
    qty_reliable_since: string | null;
  };
  fy_monthly_reports?: {
    fy_start_year: number;
    fy_label: string;
    fy_total: number;
    months: Array<{
      year: number;
      month: number;
      label: string;
      count: number;
    }>;
  } | null;
  summary: {
    total_report_events: number;
    distinct_part_customer_pairs: number;
    repeated_part_pairs: number;
    rhythm_part_pairs: Record<string, number>;
  };
  customers: Array<{
    id: number | null;
    vendor_code: string | null;
    name: string;
    avg_reports_per_day: number;
    total_reports: number;
    distinct_parts: number;
    parts: Array<{
      part_no: string;
      description: string;
      report_count: number;
      median_quantity?: number | null;
      is_repeat: boolean;
      first_report_date: string;
      last_report_date: string;
      median_interval_days: number | null;
      days_since_last_report: number;
      avg_reports_per_day_in_span: number;
      rhythm: string;
    }>;
  }>;
};

type FirIntelPart = FirIntel["customers"][number]["parts"][number];

type IntelSortPreset =
  | "part_asc"
  | "part_desc"
  | "description_asc"
  | "description_desc"
  | "reports_desc"
  | "reports_asc"
  | "qty_desc"
  | "qty_asc"
  | "gap_desc"
  | "gap_asc"
  | "since_desc"
  | "since_asc"
  | "rhythm_asc"
  | "rhythm_desc"
  | "span_desc"
  | "span_asc";

function filterAndSortIntelParts(
  parts: FirIntelPart[],
  partQ: string,
  descQ: string,
  rhythm: string,
  repeat: "all" | "yes" | "no",
  preset: IntelSortPreset,
): FirIntelPart[] {
  let rows = [...parts];
  const pq = partQ.trim().toLowerCase();
  if (pq) rows = rows.filter((p) => p.part_no.toLowerCase().includes(pq));
  const dq = descQ.trim().toLowerCase();
  if (dq) rows = rows.filter((p) => (p.description || "").toLowerCase().includes(dq));
  if (rhythm.trim()) {
    const r = rhythm.trim().toLowerCase();
    rows = rows.filter((p) => p.rhythm.toLowerCase() === r);
  }
  if (repeat === "yes") rows = rows.filter((p) => p.is_repeat);
  if (repeat === "no") rows = rows.filter((p) => !p.is_repeat);

  const dir = preset.endsWith("_desc") ? -1 : 1;
  const cmpStr = (a: string, b: string) => dir * a.localeCompare(b, undefined, { sensitivity: "base", numeric: true });
  const cmpNum = (a: number, b: number) => dir * (a - b);

  const nullsLast = (a: number | null | undefined, b: number | null | undefined, compare: (x: number, y: number) => number): number => {
    const na = a == null || !Number.isFinite(a);
    const nb = b == null || !Number.isFinite(b);
    if (na && nb) return 0;
    if (na) return 1;
    if (nb) return -1;
    return compare(a as number, b as number);
  };

  rows.sort((a, b) => {
    switch (preset) {
      case "part_asc":
      case "part_desc":
        return cmpStr(a.part_no, b.part_no);
      case "description_asc":
      case "description_desc":
        return cmpStr(a.description || "", b.description || "");
      case "reports_asc":
      case "reports_desc":
        return cmpNum(a.report_count, b.report_count);
      case "qty_asc":
      case "qty_desc":
        return nullsLast(a.median_quantity ?? null, b.median_quantity ?? null, (x, y) => cmpNum(x, y));
      case "gap_asc":
      case "gap_desc":
        return nullsLast(a.median_interval_days ?? null, b.median_interval_days ?? null, (x, y) => cmpNum(x, y));
      case "since_asc":
      case "since_desc":
        return cmpNum(a.days_since_last_report, b.days_since_last_report);
      case "rhythm_asc":
      case "rhythm_desc":
        return cmpStr(a.rhythm || "", b.rhythm || "");
      case "span_asc":
      case "span_desc":
        return cmpNum(a.avg_reports_per_day_in_span, b.avg_reports_per_day_in_span);
      default:
        return cmpStr(a.part_no, b.part_no);
    }
  });

  return rows;
}

function CustomerFirPartsTable({
  cust,
  intelPartQuery,
  intelDescQuery,
  intelRhythmFilter,
  intelRepeatFilter,
  intelSortPreset,
}: {
  cust: FirIntel["customers"][number];
  intelPartQuery: string;
  intelDescQuery: string;
  intelRhythmFilter: string;
  intelRepeatFilter: "all" | "yes" | "no";
  intelSortPreset: IntelSortPreset;
}) {
  const displayed = filterAndSortIntelParts(
    cust.parts,
    intelPartQuery,
    intelDescQuery,
    intelRhythmFilter,
    intelRepeatFilter,
    intelSortPreset,
  );
  const filteredOut = cust.parts.length - displayed.length;

  return (
    <div className="mt-3 overflow-x-auto">
      {filteredOut > 0 ? (
        <p className="mb-2 text-xs text-slate-500">
          Showing {displayed.length} of {cust.parts.length} parts (filters hide {filteredOut})
        </p>
      ) : null}
      {displayed.length === 0 ? (
        <p className="text-sm text-slate-500">No rows match the current filters for this customer.</p>
      ) : (
        <table className="min-w-full text-left text-xs text-slate-300">
          <thead className="border-b border-slate-800 text-slate-500">
            <tr>
              <th className="py-2 pr-3">Part</th>
              <th className="py-2 pr-3">Description</th>
              <th className="py-2 pr-2">Reports</th>
              <th
                className="py-2 pr-2"
                title="Median of quantities on FIR rows in this month (optional cutoff date on server)"
              >
                Expected QTY
              </th>
              <th className="py-2 pr-2">Repeat</th>
              <th className="py-2 pr-2">Median gap (d)</th>
              <th className="py-2 pr-2">Since last</th>
              <th className="py-2 pr-2">Rhythm</th>
              <th className="py-2">Span avg/d</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/80">
            {displayed.map((p) => (
              <tr key={`${cust.id ?? "u"}-${p.part_no}`}>
                <td className="py-2 pr-3 font-mono text-slate-200">{p.part_no}</td>
                <td className="max-w-[200px] truncate py-2 pr-3 text-slate-400" title={p.description}>
                  {p.description || "—"}
                </td>
                <td className="py-2 pr-2">{p.report_count}</td>
                <td className="py-2 pr-2 tabular-nums" title="Median quantity for this part in the selected month">
                  {formatExpectedQty(p.median_quantity)}
                </td>
                <td className="py-2 pr-2">{p.is_repeat ? "yes" : "no"}</td>
                <td className="py-2 pr-2">{p.median_interval_days ?? "—"}</td>
                <td className="py-2 pr-2">{p.days_since_last_report}d</td>
                <td className="py-2 pr-2 capitalize text-amber-200/90">{p.rhythm}</td>
                <td className="py-2">{p.avg_reports_per_day_in_span}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

const INTEL_TABLE_SORT_OPTIONS: { value: IntelSortPreset; label: string }[] = [
  { value: "part_asc", label: "Part A→Z" },
  { value: "part_desc", label: "Part Z→A" },
  { value: "description_asc", label: "Description A→Z" },
  { value: "description_desc", label: "Description Z→A" },
  { value: "reports_desc", label: "Reports (high → low)" },
  { value: "reports_asc", label: "Reports (low → high)" },
  { value: "qty_desc", label: "Expected QTY (high → low)" },
  { value: "qty_asc", label: "Expected QTY (low → high)" },
  { value: "gap_desc", label: "Median gap (high → low)" },
  { value: "gap_asc", label: "Median gap (low → high)" },
  { value: "since_desc", label: "Since last (most days first)" },
  { value: "since_asc", label: "Since last (fewest days first)" },
  { value: "rhythm_asc", label: "Rhythm A→Z" },
  { value: "rhythm_desc", label: "Rhythm Z→A" },
  { value: "span_desc", label: "Span avg/d (high → low)" },
  { value: "span_asc", label: "Span avg/d (low → high)" },
];

function formatExpectedQty(medianQuantity: number | null | undefined): string {
  if (medianQuantity == null || !Number.isFinite(medianQuantity)) return "—";
  if (Number.isInteger(medianQuantity)) return String(medianQuantity);
  const rounded = Math.round(medianQuantity * 10_000) / 10_000;
  return String(rounded).replace(/(\.\d*?[1-9])0+$/, "$1").replace(/\.0+$/, "");
}

function FirFyReportsBarChart({
  fyLabel,
  months,
  fyTotal,
}: {
  fyLabel: string;
  fyTotal: number;
  months: Array<{ label: string; count: number }>;
}) {
  const max = Math.max(1, ...months.map((m) => m.count));
  const title = `FIR reports by month — FY ${fyLabel}`;
  const subtitle = `April–March · ${fyTotal.toLocaleString()} FIR rows by invoice date (same basis as admin Usage)`;
  return (
    <div
      className="rounded-lg border border-slate-800 bg-slate-950/50 p-4"
      role="img"
      aria-label={`${title}. ${subtitle}`}
    >
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{title}</p>
      <p className="mt-1 text-xs text-slate-500">{subtitle}</p>
      <div className="mt-6 flex items-end gap-1 sm:gap-2">
        {months.map((m, i) => (
          <div
            key={`fy-${fyLabel}-${m.label}-${i}`}
            className="flex min-w-0 flex-1 flex-col items-center gap-1"
          >
            <span className="text-[10px] font-semibold tabular-nums text-slate-200 sm:text-xs">{m.count}</span>
            <div className="flex h-36 w-full items-end justify-center">
              <div
                className="w-[85%] max-w-10 rounded-t bg-blue-600/90 transition-[height] duration-150"
                style={{
                  height: `${m.count === 0 ? 0 : Math.max(8, (m.count / max) * 100)}%`,
                }}
                title={`${m.label}: ${m.count}`}
              />
            </div>
            <span className="w-full truncate text-center text-[9px] text-slate-500 sm:text-[10px]">{m.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function IntelStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
      <p className="text-xs uppercase text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-semibold text-white">{value}</p>
    </div>
  );
}

export default function AdminCompanyFirIntelligencePage() {
  const { id } = useParams();
  const nav = useNavigate();
  const [company, setCompany] = useState<Company | null>(null);
  const [intel, setIntel] = useState<FirIntel | null>(null);
  const [intelMonths, setIntelMonths] = useState<FirIntelMonthRow[] | null>(null);
  const [intelYm, setIntelYm] = useState("");
  const [intelReportScope, setIntelReportScope] = useState<"single_month" | "full_year">("single_month");
  const [intelPickerFyStart, setIntelPickerFyStart] = useState<number | "">("");
  const [intelErr, setIntelErr] = useState<string | null>(null);
  const [intelPartQuery, setIntelPartQuery] = useState("");
  const [intelDescQuery, setIntelDescQuery] = useState("");
  const [intelRhythmFilter, setIntelRhythmFilter] = useState("");
  const [intelRepeatFilter, setIntelRepeatFilter] = useState<"all" | "yes" | "no">("all");
  const [intelSortPreset, setIntelSortPreset] = useState<IntelSortPreset>("part_asc");

  const intelFyOptions = useMemo(() => {
    if (!intelMonths?.length) return [];
    const set = new Set<number>();
    for (const r of intelMonths) {
      if (r.year < 2000 || r.year > 2100) continue;
      set.add(fyAprilStartFromCalendarMonth(r.year, r.month));
    }
    return [...set].sort((a, b) => b - a);
  }, [intelMonths]);

  const monthsInSelectedFy = useMemo(() => {
    if (!intelMonths || intelPickerFyStart === "") return [];
    return intelMonths
      .filter(
        (r) =>
          r.year >= 2000 &&
          r.year <= 2100 &&
          fyAprilStartFromCalendarMonth(r.year, r.month) === intelPickerFyStart,
      )
      .sort((a, b) => (a.year !== b.year ? b.year - a.year : b.month - a.month));
  }, [intelMonths, intelPickerFyStart]);

  const loadCompany = useCallback(async () => {
    if (!id) return;
    const cid = Number(id);
    const c = await apiFetch<Company>(`/admin/companies/${cid}`, { token: "admin" });
    setCompany(c);
  }, [id]);

  const loadIntelMonths = useCallback(async () => {
    if (!id) return;
    const cid = Number(id);
    try {
      const rows = await apiFetch<FirIntelMonthRow[]>(`/admin/companies/${cid}/fir-intelligence-months`, {
        token: "admin",
      });
      setIntelMonths(rows);
      setIntelErr(null);
      const sane = rows.filter((r) => r.year >= 2000 && r.year <= 2100);
      setIntelPickerFyStart((prev) => {
        if (!sane.length) return "";
        const latestFy = fyAprilStartFromCalendarMonth(sane[0].year, sane[0].month);
        if (prev !== "" && sane.some((r) => fyAprilStartFromCalendarMonth(r.year, r.month) === prev)) return prev;
        return latestFy;
      });
      setIntelYm((prev) => {
        if (prev) {
          const ok = sane.some((r) => `${r.year}-${String(r.month).padStart(2, "0")}` === prev);
          if (ok) return prev;
        }
        if (!sane.length) return "";
        return `${sane[0].year}-${String(sane[0].month).padStart(2, "0")}`;
      });
    } catch (e) {
      setIntelMonths([]);
      setIntelErr(e instanceof Error ? e.message : "Failed to load FIR months");
    }
  }, [id]);

  const loadIntel = useCallback(async () => {
    if (!id) return;
    const cid = Number(id);
    setIntelErr(null);
    if (intelReportScope === "full_year") {
      if (intelPickerFyStart === "") {
        setIntel(null);
        return;
      }
      setIntel(null);
      try {
        const fi = await apiFetch<FirIntel>(`/admin/companies/${cid}/fir-intelligence?year=${intelPickerFyStart}`, {
          token: "admin",
        });
        setIntel(fi);
      } catch (e) {
        setIntelErr(e instanceof Error ? e.message : "Failed to load FIR intelligence");
        setIntel(null);
      }
      return;
    }
    if (!intelYm) {
      setIntel(null);
      return;
    }
    const [y, m] = intelYm.split("-").map(Number);
    setIntel(null);
    try {
      const fi = await apiFetch<FirIntel>(`/admin/companies/${cid}/fir-intelligence?year=${y}&month=${m}`, {
        token: "admin",
      });
      setIntel(fi);
    } catch (e) {
      setIntelErr(e instanceof Error ? e.message : "Failed to load FIR intelligence");
      setIntel(null);
    }
  }, [id, intelReportScope, intelPickerFyStart, intelYm]);

  useEffect(() => {
    setIntelMonths(null);
    setIntelYm("");
    setIntelPickerFyStart("");
    setIntelReportScope("single_month");
    setIntel(null);
    setIntelErr(null);
    setIntelPartQuery("");
    setIntelDescQuery("");
    setIntelRhythmFilter("");
    setIntelRepeatFilter("all");
    setIntelSortPreset("part_asc");
  }, [id]);

  useEffect(() => {
    if (intelReportScope !== "single_month" || !intelMonths?.length || intelPickerFyStart === "") return;
    const inY = intelMonths
      .filter((r) => fyAprilStartFromCalendarMonth(r.year, r.month) === intelPickerFyStart)
      .sort((a, b) => (a.year !== b.year ? b.year - a.year : b.month - a.month));
    const nextYm = inY.length ? `${inY[0].year}-${String(inY[0].month).padStart(2, "0")}` : "";
    setIntelYm((cur) => {
      if (cur && inY.some((r) => `${r.year}-${String(r.month).padStart(2, "0")}` === cur)) return cur;
      return nextYm;
    });
  }, [intelReportScope, intelPickerFyStart, intelMonths]);

  useEffect(() => {
    setIntelPartQuery("");
    setIntelDescQuery("");
    setIntelRhythmFilter("");
    setIntelRepeatFilter("all");
    setIntelSortPreset("part_asc");
  }, [intelYm, intelReportScope, intelPickerFyStart]);

  useEffect(() => {
    const t = localStorage.getItem("fir_admin_token");
    if (!t) {
      nav("/login");
      return;
    }
    setCompany(null);
    loadCompany().catch(() => nav("/login"));
    void loadIntelMonths();
  }, [id, nav, loadCompany, loadIntelMonths]);

  useEffect(() => {
    void loadIntel();
  }, [loadIntel]);

  if (!company) {
    return <p className="text-slate-400">Loading…</p>;
  }

  const companyBase = `/admin/companies/${company.id}`;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link className="text-sm text-brand-600 hover:underline" to={companyBase}>
          ← Back to tenant
        </Link>
        <Link className="text-sm text-slate-500 hover:text-slate-300 hover:underline" to="/admin">
          Admin home
        </Link>
      </div>
      <div>
        <h1 className="text-2xl font-semibold text-white">FIR intelligence</h1>
        <p className="mt-1 text-sm text-slate-400">
          {company.company_name} · Vendor <span className="font-mono text-slate-200">{company.vendor_code}</span>
        </p>
      </div>

      {intelErr ? <p className="text-sm text-red-400">{intelErr}</p> : null}

      <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 space-y-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
          <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-500" htmlFor="intel-year-select">
                Financial year <span className="text-slate-600">(Apr–Mar)</span>
              </label>
              <select
                id="intel-year-select"
                className="min-w-[10rem] rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none ring-brand-600 focus:ring-2"
                value={intelPickerFyStart === "" ? "" : String(intelPickerFyStart)}
                disabled={intelMonths === null || intelFyOptions.length === 0}
                onChange={(e) => {
                  const v = e.target.value;
                  setIntelPickerFyStart(v === "" ? "" : Number(v));
                }}
              >
                {intelMonths === null ? (
                  <option value="">Loading…</option>
                ) : intelFyOptions.length === 0 ? (
                  <option value="">No FY with data</option>
                ) : (
                  intelFyOptions.map((fy) => (
                    <option key={fy} value={fy}>
                      {formatFyRangeLabel(fy)}
                    </option>
                  ))
                )}
              </select>
          </div>
          <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-500" htmlFor="intel-scope-select">
                View
              </label>
              <select
                id="intel-scope-select"
                className="min-w-[12rem] rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none ring-brand-600 focus:ring-2"
                value={intelReportScope}
                disabled={intelMonths === null || (intelMonths?.length ?? 0) === 0}
                onChange={(e) => setIntelReportScope(e.target.value as "single_month" | "full_year")}
              >
                <option value="single_month">Single month</option>
                <option value="full_year">Full financial year</option>
              </select>
            </div>
            {intelReportScope === "single_month" ? (
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-slate-500" htmlFor="intel-month-select">
                  Month <span className="text-slate-600">(within FY)</span>
                </label>
                <select
                  id="intel-month-select"
                  className="min-w-[16rem] rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none ring-brand-600 focus:ring-2"
                  value={intelYm}
                  disabled={
                    intelMonths === null ||
                    (intelMonths?.length ?? 0) === 0 ||
                    intelPickerFyStart === "" ||
                    monthsInSelectedFy.length === 0
                  }
                  onChange={(e) => setIntelYm(e.target.value)}
                >
                  {intelMonths === null ? (
                    <option value="">Loading months…</option>
                  ) : intelPickerFyStart === "" || monthsInSelectedFy.length === 0 ? (
                    <option value="">No months in this FY</option>
                  ) : (
                    monthsInSelectedFy.map((r) => {
                      const v = `${r.year}-${String(r.month).padStart(2, "0")}`;
                      return (
                        <option key={v} value={v}>
                          {r.label}
                        </option>
                      );
                    })
                  )}
                </select>
              </div>
            ) : null}
        </div>

        {intelMonths === null ? (
          <p className="text-sm text-slate-500">Loading months…</p>
        ) : intelMonths.length === 0 ? (
          <p className="text-sm text-slate-500">No FIR intelligence data for this tenant yet.</p>
        ) : intelReportScope === "full_year" && intelPickerFyStart === "" ? (
          <p className="text-sm text-amber-200/90">Choose a financial year above.</p>
        ) : intelReportScope === "single_month" && !intelYm ? (
          <p className="text-sm text-amber-200/90">Choose a month for the selected financial year.</p>
        ) : intel ? (
          <>
            {intel.fy_monthly_reports ? (
              <FirFyReportsBarChart
                fyLabel={intel.fy_monthly_reports.fy_label}
                months={intel.fy_monthly_reports.months}
                fyTotal={intel.fy_monthly_reports.fy_total}
              />
            ) : null}

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 text-sm">
              <IntelStat
                label={`FIR rows (this ${intel.view?.scope === "financial_year" ? "FY" : "month"})`}
                value={intel.summary.total_report_events}
              />
              <IntelStat
                label={`Part × customer pairs (this ${intel.view?.scope === "financial_year" ? "FY" : "month"})`}
                value={intel.summary.distinct_part_customer_pairs}
              />
              <IntelStat
                label={`Repeating pairs (2+) — ${intel.view?.scope === "financial_year" ? "FY" : "month"}`}
                value={intel.summary.repeated_part_pairs}
              />
              <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                <p className="text-xs uppercase text-slate-500">By rhythm (pairs)</p>
                <p className="mt-1 text-slate-300">
                  {Object.entries(intel.summary.rhythm_part_pairs)
                    .map(([k, v]) => `${k}: ${v}`)
                    .join(" · ") || "—"}
                </p>
              </div>
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Filters &amp; sort</p>
              <div className="mt-3 flex flex-col gap-3 lg:flex-row lg:flex-wrap lg:items-end">
                <div className="min-w-[10rem] flex-1">
                  <label className="block text-xs text-slate-500" htmlFor="intel-filter-part">
                    Part contains
                  </label>
                  <input
                    id="intel-filter-part"
                    type="search"
                    autoComplete="off"
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white outline-none ring-brand-600 focus:ring-2"
                    value={intelPartQuery}
                    onChange={(e) => setIntelPartQuery(e.target.value)}
                    placeholder="e.g. MB12"
                  />
                </div>
                <div className="min-w-[10rem] flex-1">
                  <label className="block text-xs text-slate-500" htmlFor="intel-filter-desc">
                    Description contains
                  </label>
                  <input
                    id="intel-filter-desc"
                    type="search"
                    autoComplete="off"
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white outline-none ring-brand-600 focus:ring-2"
                    value={intelDescQuery}
                    onChange={(e) => setIntelDescQuery(e.target.value)}
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-500" htmlFor="intel-filter-rhythm">
                    Rhythm
                  </label>
                  <select
                    id="intel-filter-rhythm"
                    className="mt-1 min-w-[9rem] rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white outline-none ring-brand-600 focus:ring-2"
                    value={intelRhythmFilter}
                    onChange={(e) => setIntelRhythmFilter(e.target.value)}
                  >
                    <option value="">All</option>
                    <option value="running">Running</option>
                    <option value="regular">Regular</option>
                    <option value="occasional">Occasional</option>
                    <option value="stranger">Stranger</option>
                    <option value="new">New</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-slate-500" htmlFor="intel-filter-repeat">
                    Repeat
                  </label>
                  <select
                    id="intel-filter-repeat"
                    className="mt-1 min-w-[8rem] rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white outline-none ring-brand-600 focus:ring-2"
                    value={intelRepeatFilter}
                    onChange={(e) => setIntelRepeatFilter(e.target.value as "all" | "yes" | "no")}
                  >
                    <option value="all">All</option>
                    <option value="yes">Yes</option>
                    <option value="no">No</option>
                  </select>
                </div>
                <div className="min-w-[14rem] flex-1">
                  <label className="block text-xs text-slate-500" htmlFor="intel-sort">
                    Sort
                  </label>
                  <select
                    id="intel-sort"
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white outline-none ring-brand-600 focus:ring-2"
                    value={intelSortPreset}
                    onChange={(e) => setIntelSortPreset(e.target.value as IntelSortPreset)}
                  >
                    {INTEL_TABLE_SORT_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </div>
                <button
                  type="button"
                  className="rounded-lg border border-slate-600 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-800"
                  onClick={() => {
                    setIntelPartQuery("");
                    setIntelDescQuery("");
                    setIntelRhythmFilter("");
                    setIntelRepeatFilter("all");
                    setIntelSortPreset("part_asc");
                  }}
                >
                  Clear filters
                </button>
              </div>
            </div>

            <div className="space-y-8">
              {intel.customers.map((cust) => (
                <div key={`${cust.id ?? "u"}-${cust.name}`} className="rounded-xl border border-slate-800 bg-slate-950/30 p-4">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <h3 className="text-base font-semibold text-white">{cust.name}</h3>
                    <p className="text-xs text-slate-500">
                      {cust.vendor_code ? <span className="font-mono text-slate-400">{cust.vendor_code}</span> : null}
                      {cust.vendor_code ? " · " : null}
                      avg {cust.avg_reports_per_day}/day · {cust.total_reports} FIR rows (
                      {intel.view?.scope === "financial_year" ? "FY" : "month"}) · {cust.distinct_parts} parts
                    </p>
                  </div>
                  {cust.parts.length === 0 ? (
                    <p className="mt-2 text-sm text-slate-500">
                      No FIR intelligence rows for this customer in this {intel.view?.scope === "financial_year" ? "FY" : "month"}.
                    </p>
                  ) : (
                    <CustomerFirPartsTable
                      cust={cust}
                      intelPartQuery={intelPartQuery}
                      intelDescQuery={intelDescQuery}
                      intelRhythmFilter={intelRhythmFilter}
                      intelRepeatFilter={intelRepeatFilter}
                      intelSortPreset={intelSortPreset}
                    />
                  )}
                </div>
              ))}
            </div>
          </>
        ) : (
          <p className="text-sm text-slate-500">Loading…</p>
        )}
      </div>
    </div>
  );
}
