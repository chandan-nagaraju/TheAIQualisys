import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import JSZip from "jszip";
import { apiFetch, firPreviewUrl, workspaceFetch } from "../../api";

type FirSubscriptionGate = {
  enable_subscription: boolean;
  trial_active: boolean;
  subscription_active: boolean;
};

type Row = Record<string, unknown> & {
  draw_rev?: string;
  sample_size?: number | string;
  num_params?: number;
};

type EnrichRes = { rows: Row[]; customer: { vendor_code: string; name: string } | null; current_date: string };

type FirQuota = {
  allowed_for_n: boolean;
  message: string | null;
  invoices_this_month: number;
  fir_reports_this_month: number;
  usage_this_month: number;
  usage_limit: number | null;
  remaining: number | null;
  would_remain_after_n: number | null;
};

function previewParamsForRow(r: Row, cust: EnrichRes["customer"], currentDate: string): Record<string, string> {
  const partName = String(r["Part Number"] ?? "").trim();
  const description = String(r["Description"] ?? "").trim() || "-";
  const drawRev = String(r.draw_rev ?? "");
  const invoiceNo = String(r["Invoice Number"] ?? "").trim();
  const quantity = String(r["Quantity"] ?? "").trim();
  const sampleSize = String(r.sample_size ?? "");
  const noOfParams = String(r.num_params ?? "17");
  const vendorCode = cust?.vendor_code ?? "";
  const customerName = cust?.name ?? "";
  return {
    partName,
    description,
    drawRev,
    invoiceNo,
    quantity,
    sampleSize,
    noOfParams,
    vendorCode,
    customer: customerName,
    reportNo: "1",
    reportDate: currentDate,
  };
}

export default function InspectionResultsPage() {
  const loc = useLocation();
  const nav = useNavigate();
  const st = loc.state as { rows: Record<string, unknown>[] } | null;
  const [data, setData] = useState<EnrichRes | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const iframeRefs = useRef<(HTMLIFrameElement | null)[]>([]);
  const previewsSectionRef = useRef<HTMLDivElement | null>(null);

  const [embedsReady, setEmbedsReady] = useState(false);
  const [embedWaitTimedOut, setEmbedWaitTimedOut] = useState(false);
  const [autofillApplied, setAutofillApplied] = useState(false);
  const [zipping, setZipping] = useState(false);
  const [batchMsg, setBatchMsg] = useState<string | null>(null);
  const [batchErr, setBatchErr] = useState<string | null>(null);
  const [firQuota, setFirQuota] = useState<FirQuota | null>(null);
  const [firEntitled, setFirEntitled] = useState<"loading" | "yes" | "no">("loading");

  useEffect(() => {
    let cancelled = false;
    apiFetch<FirSubscriptionGate>("/subscription/status")
      .then((s) => {
        if (cancelled) return;
        const entitled = s.trial_active || s.subscription_active;
        if (s.enable_subscription || entitled) setFirEntitled("yes");
        else setFirEntitled("no");
      })
      .catch(() => {
        if (!cancelled) setFirEntitled("yes");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!st?.rows?.length) return;
    workspaceFetch<EnrichRes>("/api/app/inspection/enrich", {
      method: "POST",
      body: JSON.stringify({ rows: st.rows }),
    })
      .then(setData)
      .catch((e) => setErr(e.message));
  }, [st?.rows]);

  useEffect(() => {
    if (!data?.rows?.length) {
      setFirQuota(null);
      return;
    }
    const n = data.rows.length;
    workspaceFetch<FirQuota>(`/api/app/inspection/fir-quota?n=${n}`)
      .then(setFirQuota)
      .catch(() => setFirQuota(null));
  }, [data?.rows]);

  const previewUrls = useMemo(() => {
    if (!data?.rows.length) return [];
    return data.rows.map((r) => firPreviewUrl(previewParamsForRow(r, data.customer, data.current_date)));
  }, [data]);

  useEffect(() => {
    if (!data?.rows.length || previewUrls.length === 0) return;
    setEmbedsReady(false);
    setEmbedWaitTimedOut(false);
    setAutofillApplied(false);
    setBatchMsg(null);
    setBatchErr(null);
    let attempts = 0;
    const maxAttempts = 200;
    const id = window.setInterval(() => {
      attempts++;
      const n = data.rows.length;
      const frames = iframeRefs.current.slice(0, n);
      if (frames.length < n || frames.some((f) => !f)) return;
      let all = true;
      for (const f of frames) {
        try {
          const api = f?.contentWindow?.FIR_PREVIEW_API;
          if (!api?.ready) {
            all = false;
            break;
          }
        } catch {
          all = false;
          break;
        }
      }
      if (all) {
        setEmbedsReady(true);
        window.clearInterval(id);
      } else if (attempts >= maxAttempts) {
        setEmbedWaitTimedOut(true);
        window.clearInterval(id);
      }
    }, 200);
    return () => window.clearInterval(id);
  }, [data, previewUrls.length]);

  useEffect(() => {
    if (!autofillApplied) return;
    previewsSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [autofillApplied]);

  const runAutofillAll = useCallback(() => {
    if (!data?.rows.length) return;
    setBatchErr(null);
    setBatchMsg(null);
    const n = data.rows.length;
    const failures: string[] = [];
    for (let i = 0; i < n; i++) {
      const f = iframeRefs.current[i];
      try {
        const w = f?.contentWindow as (Window & { FIR_PREVIEW_API?: { autoFillMeasuredValues?: () => void } }) | null;
        if (!w?.FIR_PREVIEW_API?.autoFillMeasuredValues) {
          failures.push(`#${i + 1}: preview API not available (reload page; avoid opening FIR on a different port than this app)`);
          continue;
        }
        w.FIR_PREVIEW_API.autoFillMeasuredValues();
      } catch (e) {
        failures.push(`#${i + 1}: ${e instanceof Error ? e.message : "blocked"}`);
      }
    }
    if (failures.length === n) {
      setBatchErr(
        failures[0] +
          " — FIR previews must load from the same host as this UI (e.g. /api/… via Vite proxy). Do not use VITE_API_URL for preview URLs.",
      );
      return;
    }
    if (failures.length) {
      setBatchErr(`Some rows skipped: ${failures.join(" · ")}`);
    }
    setAutofillApplied(true);
    setBatchMsg(
      "Measured values are filled in the live previews below (scroll down). Check them here first, then use Download all as ZIP.",
    );
  }, [data]);

  const downloadAllZip = useCallback(async () => {
    if (!data?.rows.length) return;
    setBatchErr(null);
    setZipping(true);
    try {
      const n = data.rows.length;
      const q = await workspaceFetch<FirQuota>(`/api/app/inspection/fir-quota?n=${n}`);
      if (!q.allowed_for_n) {
        throw new Error(q.message || "Not allowed to record this many FIR reports under your plan.");
      }
      const zip = new JSZip();
      for (let i = 0; i < n; i++) {
        const f = iframeRefs.current[i];
        const gen = f?.contentWindow?.FIR_PREVIEW_API?.generatePdfBlob;
        if (!gen) throw new Error(`Report ${i + 1} is not ready for PDF export.`);
        const result = await gen();
        const name = (result.filename || `FIR_${i + 1}.pdf`).replace(/[/\\]/g, "_");
        zip.file(name, result.blob);
      }
      const blob = await zip.generateAsync({ type: "blob" });
      const stamp = (data.current_date || "batch").replace(/\W+/g, "_");
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `FIR_reports_${stamp}.zip`;
      a.click();
      URL.revokeObjectURL(a.href);
      try {
        await workspaceFetch<{
          recorded: number;
          usage_this_month: number;
          usage_limit: number | null;
          fir_reports_this_month: number;
        }>("/api/app/inspection/record-reports", {
          method: "POST",
          body: JSON.stringify({ rows: data.rows }),
        });
      } catch (recErr) {
        setBatchErr(
          `${recErr instanceof Error ? recErr.message : "Failed to log FIR usage"}. The ZIP file was still downloaded; contact support if billing did not update.`,
        );
        return;
      }
      const q2 = await workspaceFetch<FirQuota>(`/api/app/inspection/fir-quota?n=${n}`);
      setFirQuota(q2);
      setBatchMsg(
        `ZIP download started. Logged ${n} FIR report(s). Usage this month: ${q2.usage_this_month}${
          q2.usage_limit != null ? ` / ${q2.usage_limit}` : " (unlimited)"
        }.`,
      );
    } catch (e) {
      setBatchErr(e instanceof Error ? e.message : "ZIP build failed");
    } finally {
      setZipping(false);
    }
  }, [data]);

  function openPreview(r: Row) {
    if (!data) return;
    const url = firPreviewUrl(previewParamsForRow(r, data.customer, data.current_date));
    window.open(url, "_blank", "noopener,noreferrer");
  }

  if (!st?.rows?.length) {
    return (
      <div className="rounded-xl border bg-white p-6">
        <p>No results. </p>
        <button className="text-blue-700 underline" type="button" onClick={() => nav("/workspace/upload")}>
          Start over
        </button>
      </div>
    );
  }

  if (firEntitled === "loading") {
    return <p className="text-slate-600">Checking access…</p>;
  }
  if (firEntitled === "no") {
    return <Navigate to="/upgrade" replace state={{ workspaceBlocked: true }} />;
  }

  if (err) {
    return <p className="text-red-600">{err}</p>;
  }
  if (!data) {
    return <p className="text-slate-600">Loading…</p>;
  }

  const cust = data.customer;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h1 className="text-xl font-semibold text-slate-900">Inspection results</h1>
      {cust && (
        <p className="mt-1 text-sm text-slate-600">
          Vendor: <span className="font-mono">{cust.vendor_code}</span> — {cust.name}
        </p>
      )}

      <div className="mt-6 rounded-lg border border-slate-200 bg-slate-50 p-4">
        <h2 className="text-sm font-semibold text-slate-800">Batch FIR tools</h2>
        {firQuota && (
          <p className="mt-2 text-xs text-slate-700">
            <strong>Usage (billing)</strong>: {firQuota.usage_this_month}
            {firQuota.usage_limit != null ? ` / ${firQuota.usage_limit}` : " (unlimited)"} this month — v2 invoices{" "}
            {firQuota.invoices_this_month} + FIR reports {firQuota.fir_reports_this_month} (same monthly cap).{" "}
            {firQuota.usage_limit != null &&
              firQuota.would_remain_after_n != null &&
              firQuota.allowed_for_n && (
                <span>
                  After this ZIP: <strong>{firQuota.would_remain_after_n}</strong> slot(s) left.
                </span>
              )}
            {!firQuota.allowed_for_n && firQuota.message && (
              <span className="mt-1 block text-amber-800">{firQuota.message}</span>
            )}
          </p>
        )}
        <p className="mt-1 text-xs text-slate-600">
          Each row has a <strong>live FIR preview</strong> below (same page as this table).{" "}
          <strong>Auto-fill all</strong> fills those previews in place — scroll down to see measured values. The ZIP is built
          from those same previews. <strong>Preview FIR</strong> in the table opens a <em>new</em> browser tab with a fresh
          copy (it will not show batch auto-fill unless you click auto-fill there too).
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={!embedsReady || zipping}
            className="rounded px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-400"
            style={{ backgroundColor: embedsReady && !zipping ? "#17a2b8" : undefined }}
            onClick={runAutofillAll}
          >
            Auto-fill all measured values
          </button>
          <button
            type="button"
            disabled={!autofillApplied || zipping || (firQuota != null && !firQuota.allowed_for_n)}
            className="rounded bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:cursor-not-allowed disabled:bg-slate-400"
            onClick={() => void downloadAllZip()}
          >
            {zipping ? "Building ZIP…" : "Download all reports as ZIP"}
          </button>
        </div>
        {!embedsReady && !embedWaitTimedOut && (
          <p className="mt-2 text-xs text-amber-800">Loading FIR previews below…</p>
        )}
        {embedWaitTimedOut && !embedsReady && (
          <p className="mt-2 text-xs text-red-700">
            Some previews did not become ready (invalid part data or network). You can still use <strong>Preview FIR</strong>{" "}
            per row.
          </p>
        )}
        {embedsReady && !autofillApplied && (
          <p className="mt-2 text-xs text-slate-600">When ready, click auto-fill — then review the previews below before ZIP.</p>
        )}
        {batchMsg && <p className="mt-2 text-sm text-green-700">{batchMsg}</p>}
        {batchErr && <p className="mt-2 text-sm text-red-600">{batchErr}</p>}
      </div>

      <div className="mt-4 overflow-x-auto">
        <table className="min-w-full border-collapse text-sm">
          <thead>
            <tr className="bg-slate-100">
              <th className="border px-2 py-1">Part Number</th>
              <th className="border px-2 py-1">Description</th>
              <th className="border px-2 py-1">Draw Rev</th>
              <th className="border px-2 py-1">Qty</th>
              <th className="border px-2 py-1">Invoice</th>
              <th className="border px-2 py-1">Sample</th>
              <th className="border px-2 py-1">Params</th>
              <th className="border px-2 py-1">FIR</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r, i) => (
              <tr key={i}>
                <td className="border px-2 py-1">{String(r["Part Number"] ?? "")}</td>
                <td className="border px-2 py-1">{String(r["Description"] ?? "")}</td>
                <td className="border px-2 py-1">{String(r.draw_rev ?? "")}</td>
                <td className="border px-2 py-1">{String(r["Quantity"] ?? "")}</td>
                <td className="border px-2 py-1">{String(r["Invoice Number"] ?? "")}</td>
                <td className="border px-2 py-1">{String(r.sample_size ?? "")}</td>
                <td className="border px-2 py-1">{String(r.num_params ?? "")}</td>
                <td className="border px-2 py-1">
                  <button
                    type="button"
                    className="text-blue-700 underline"
                    title="New tab = fresh report. Batch auto-fill only updates the embedded previews below."
                    onClick={() => openPreview(r)}
                  >
                    Preview FIR (new tab)
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Visible iframes: same DOM instances used for auto-fill + ZIP (not the off-screen copies) */}
      <div ref={previewsSectionRef} className="mt-10 border-t border-slate-200 pt-8">
        <h2 className="text-lg font-semibold text-slate-900">Live FIR previews</h2>
        <p className="mt-1 text-sm text-slate-600">
          These panels are the reports used for <strong>Auto-fill all</strong> and <strong>Download ZIP</strong>. After
          auto-fill, measured values should appear here before you download.
        </p>
        <div className="mt-6 space-y-10">
          {data.rows.map((r, i) => {
            const partNo = String(r["Part Number"] ?? "").trim();
            const inv = String(r["Invoice Number"] ?? "").trim();
            return (
              <div key={`${i}-${previewUrls[i]?.slice(0, 40)}`} className="rounded-lg border border-slate-200 bg-slate-50/80 p-3 shadow-sm">
                <p className="mb-2 text-sm font-medium text-slate-800">
                  Part <span className="font-mono">{partNo || "—"}</span>
                  {inv ? (
                    <>
                      {" "}
                      · Invoice <span className="font-mono">{inv}</span>
                    </>
                  ) : null}
                </p>
                <iframe
                  title={`FIR preview ${partNo || i + 1}`}
                  src={previewUrls[i]}
                  className="block h-[min(85vh,920px)] w-full max-w-[1200px] rounded border border-slate-300 bg-white shadow-inner"
                  ref={(el) => {
                    iframeRefs.current[i] = el;
                  }}
                />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
