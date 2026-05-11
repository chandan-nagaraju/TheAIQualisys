import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import JSZip from "jszip";
import { firPreviewUrl, workspaceFetch } from "../../api";

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

type FirIntelPreview = {
  rows_total: number;
  rows_invalid: number;
  prospective_new_intelligence_records: number;
  prospective_duplicate_intelligence_records: number;
};

type RecordReportsRes = {
  rows_processed: number;
  rows_invalid: number;
  new_intelligence_records: number;
  duplicate_intelligence_records: number;
  fir_reports_generated: number;
  recorded: number;
  invoices_this_month: number;
  fir_reports_this_month: number;
  usage_this_month: number;
  usage_limit: number | null;
};

async function fetchFirQuotaUsingIntelPreview(
  rows: Row[],
  sourceFile: string | null | undefined,
): Promise<FirQuota> {
  try {
    const preview = await workspaceFetch<FirIntelPreview>("/api/app/inspection/preview-fir-intelligence", {
      method: "POST",
      body: JSON.stringify({ rows, source_file: sourceFile ?? null }),
    });
    return workspaceFetch<FirQuota>(
      `/api/app/inspection/fir-quota?n=${preview.prospective_new_intelligence_records}`,
    );
  } catch {
    return workspaceFetch<FirQuota>(`/api/app/inspection/fir-quota?n=${rows.length}`);
  }
}

type FirPreviewApi = {
  ready?: boolean;
  waitForAssets?: () => Promise<void>;
  generatePdfBlob?: () => Promise<{
    blob: Blob;
    filename: string;
    byteSize?: number;
    sizeWarning?: string;
  }>;
};

/** Cross-origin PDF waits (html2pdf); large pages can be slow */
const FIR_PDF_POSTMESSAGE_TIMEOUT_MS = 240000;

/** Where to pin the fixed capture iframe (px). If previews sit far below the fold, browsers throttle PDF → 0/n. */
function computeCaptureTopPx(anchor: HTMLElement | null, iframeHeight: number): number {
  const vh = window.innerHeight;
  let topPx = anchor ? Math.max(0, Math.floor(anchor.getBoundingClientRect().top)) : Math.max(0, Math.floor(vh * 0.08));
  const bottom = topPx + iframeHeight;
  /* Anchor is mostly off-screen below */
  if (topPx > vh * 0.92) {
    topPx = Math.max(0, Math.floor(vh * 0.08));
  }
  /* Iframe would sit almost entirely above the viewport */
  if (bottom < 48) {
    topPx = Math.max(0, Math.floor(vh * 0.08));
  }
  return topPx;
}

/**
 * Browsers throttle html2pdf/html2canvas inside cross-origin iframes far from the viewport.
 * Lift the active iframe with `position: fixed` at `viewportTopPx` (see computeCaptureTopPx), same
 * pixel size as in-layout. Stack: mask z-150, main column z-220, capture iframe z-240.
 * Completely hidden outer opacity during capture (html2pdf runs inside the iframe document).
 */
async function prepareIframeForPdfCapture(f: HTMLIFrameElement | null, viewportTopPx: number): Promise<() => void> {
  if (!f) return () => {};
  const parent = f.parentElement as HTMLElement | null;
  if (!parent) return () => {};

  const rect = f.getBoundingClientRect();
  const w = Math.max(1, Math.round(rect.width));
  const h = Math.max(1, Math.round(rect.height));

  const prevParentMinHeight = parent.style.minHeight;
  const lockH = Math.ceil(parent.getBoundingClientRect().height);
  parent.style.minHeight = `${lockH}px`;

  const prevStyle = {
    position: f.style.position,
    top: f.style.top,
    left: f.style.left,
    transform: f.style.transform,
    width: f.style.width,
    height: f.style.height,
    maxWidth: f.style.maxWidth,
    zIndex: f.style.zIndex,
    pointerEvents: f.style.pointerEvents,
    opacity: f.style.opacity,
    boxShadow: f.style.boxShadow,
  };

  f.style.position = "fixed";
  f.style.top = `${Math.max(0, viewportTopPx)}px`;
  f.style.left = "0";
  f.style.transform = "none";
  f.style.width = `${w}px`;
  f.style.height = `${h}px`;
  f.style.maxWidth = "none";
  /** Above main column (z-220) so the iframe is not fully covered by the opaque tools/table stack. */
  f.style.zIndex = "240";
  f.style.pointerEvents = "none";
  /* Outer opacity only (user must not see the lifted preview); capture uses the iframe’s internal DOM. */
  f.style.opacity = "0";
  f.style.boxShadow = "none";

  await new Promise<void>((resolve) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => resolve());
    });
  });

  return () => {
    parent.style.minHeight = prevParentMinHeight;
    f.style.position = prevStyle.position;
    f.style.top = prevStyle.top;
    f.style.left = prevStyle.left;
    f.style.transform = prevStyle.transform;
    f.style.width = prevStyle.width;
    f.style.height = prevStyle.height;
    f.style.maxWidth = prevStyle.maxWidth;
    f.style.zIndex = prevStyle.zIndex;
    f.style.pointerEvents = prevStyle.pointerEvents;
    if (prevStyle.opacity) f.style.opacity = prevStyle.opacity;
    else f.style.removeProperty("opacity");
    if (prevStyle.boxShadow) f.style.boxShadow = prevStyle.boxShadow;
    else f.style.removeProperty("box-shadow");
  };
}

/**
 * Programmatic save. Keep the blob URL alive long enough for large ZIPs — revoking early cancels the download.
 */
function triggerBlobDownload(blob: Blob, filename: string): void {
  const safeName = filename.replace(/[/\\]/g, "_");
  const url = URL.createObjectURL(blob);
  const revokeMs = Math.max(10_000, Math.min(600_000, Math.floor(blob.size / 200 + 8000)));
  const a = document.createElement("a");
  a.href = url;
  a.download = safeName;
  a.rel = "noopener";
  a.style.display = "none";
  document.body.appendChild(a);
  requestAnimationFrame(() => {
    a.click();
    window.setTimeout(() => {
      try {
        if (a.parentNode) document.body.removeChild(a);
      } catch {
        /* ignore */
      }
      URL.revokeObjectURL(url);
    }, revokeMs);
  });
}

function firIframeTargetOrigin(iframe: HTMLIFrameElement | null): string {
  if (!iframe?.src) return "*";
  try {
    return new URL(iframe.src, window.location.href).origin;
  } catch {
    return "*";
  }
}

/** FIR header DATE: use invoice row date from upload when present, else server fallback (ISO → dd.mm.yyyy). */
function reportDateForFIR(r: Row, fallbackIso: string): string {
  const raw = String(r["Date"] ?? "").trim();
  if (raw) return raw;
  const m = fallbackIso.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (m) return `${m[3]}.${m[2]}.${m[1]}`;
  return fallbackIso;
}

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
    reportDate: reportDateForFIR(r, currentDate),
  };
}

export default function InspectionResultsPage() {
  const loc = useLocation();
  const nav = useNavigate();
  const st = loc.state as { rows: Row[]; filename?: string } | null;
  const [data, setData] = useState<EnrichRes | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const iframeRefs = useRef<(HTMLIFrameElement | null)[]>([]);
  const previewsSectionRef = useRef<HTMLDivElement | null>(null);
  const pdfDurationsRef = useRef<number[]>([]);
  const lastZipOfferRef = useRef<{ blob: Blob; filename: string } | null>(null);

  const [embedsReady, setEmbedsReady] = useState(false);
  const [embedWaitTimedOut, setEmbedWaitTimedOut] = useState(false);
  const [autofillApplied, setAutofillApplied] = useState(false);
  const [zipping, setZipping] = useState(false);
  const [batchMsg, setBatchMsg] = useState<string | null>(null);
  const [batchErr, setBatchErr] = useState<string | null>(null);
  const [firQuota, setFirQuota] = useState<FirQuota | null>(null);
  const [zipProgress, setZipProgress] = useState<{
    current: number;
    total: number;
    label: string;
    etaSec: number | null;
    pct: number;
  } | null>(null);
  const [zipSaveHint, setZipSaveHint] = useState(false);

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
    let cancelled = false;
    fetchFirQuotaUsingIntelPreview(data.rows, st?.filename)
      .then((q) => {
        if (!cancelled) setFirQuota(q);
      })
      .catch(() => {
        if (!cancelled) setFirQuota(null);
      });
    return () => {
      cancelled = true;
    };
  }, [data?.rows, st?.filename]);

  const previewUrls = useMemo(() => {
    if (!data?.rows.length) return [];
    return data.rows.map((r, i) =>
      firPreviewUrl({
        ...previewParamsForRow(r, data.customer, data.current_date),
        previewFrameIndex: String(i),
      }),
    );
  }, [data]);

  useEffect(() => {
    if (!data?.rows.length || previewUrls.length === 0) return;
    setEmbedsReady(false);
    setEmbedWaitTimedOut(false);
    setAutofillApplied(false);
    setBatchMsg(null);
    setBatchErr(null);
    setZipSaveHint(false);
    lastZipOfferRef.current = null;
    const n = data.rows.length;
    const ready: boolean[] = new Array(n).fill(false);

    const tryPoll = () => {
      for (let i = 0; i < n; i++) {
        if (ready[i]) continue;
        try {
          const f = iframeRefs.current[i];
          const api = f?.contentWindow?.FIR_PREVIEW_API as FirPreviewApi | undefined;
          if (api?.ready) ready[i] = true;
        } catch {
          /* cross-origin: rely on postMessage from fir_preview */
        }
      }
      if (ready.every(Boolean)) {
        setEmbedsReady(true);
      }
      return ready.every(Boolean);
    };

    const onMsg = (ev: MessageEvent) => {
      const d = ev.data;
      if (!d || d.source !== "fir-saas-fir-preview" || d.type !== "ready") return;
      if (typeof d.frameIndex === "number" && d.frameIndex >= 0 && d.frameIndex < n) {
        ready[d.frameIndex] = true;
        if (ready.every(Boolean)) setEmbedsReady(true);
      }
    };
    window.addEventListener("message", onMsg);

    let attempts = 0;
    const maxAttempts = 200;
    const id = window.setInterval(() => {
      attempts++;
      const allReady = tryPoll();
      if (allReady) {
        window.clearInterval(id);
      } else if (attempts >= maxAttempts) {
        setEmbedWaitTimedOut(true);
        window.clearInterval(id);
      }
    }, 200);
    return () => {
      window.removeEventListener("message", onMsg);
      window.clearInterval(id);
    };
  }, [data, previewUrls.length]);

  const runAutofillAll = useCallback(() => {
    if (!data?.rows.length) return;
    setBatchErr(null);
    setBatchMsg(null);
    const n = data.rows.length;
    const failures: string[] = [];
    for (let i = 0; i < n; i++) {
      const f = iframeRefs.current[i];
      if (!f?.contentWindow) {
        failures.push(`#${i + 1}: preview frame missing`);
        continue;
      }
      try {
        const w = f.contentWindow as (Window & { FIR_PREVIEW_API?: { autoFillMeasuredValues?: () => void } }) | null;
        if (w?.FIR_PREVIEW_API?.autoFillMeasuredValues) {
          w.FIR_PREVIEW_API.autoFillMeasuredValues();
          continue;
        }
      } catch {
        /* cross-origin (e.g. Amplify UI + Railway iframe): use postMessage */
      }
      f.contentWindow.postMessage(
        { source: "fir-saas-fir-preview-parent", type: "autoFill" },
        firIframeTargetOrigin(f),
      );
    }
    if (failures.length) {
      setBatchErr(`Some rows skipped: ${failures.join(" · ")}`);
    }
    setAutofillApplied(true);
    setBatchMsg("Measured values are filled in the live previews below.");
  }, [data]);

  const downloadAllZip = useCallback(async () => {
    if (!data?.rows.length) return;
    setBatchErr(null);
    setBatchMsg(null);
    setZipSaveHint(false);
    lastZipOfferRef.current = null;
    pdfDurationsRef.current = [];
    setZipping(true);
    try {
      window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    } catch {
      window.scrollTo(0, 0);
    }
    const n = data.rows.length;
    setZipProgress({
      current: 0,
      total: n,
      label: "Preparing…",
      etaSec: null,
      pct: 0,
    });
    try {
      const q = await fetchFirQuotaUsingIntelPreview(data.rows, st?.filename);
      if (!q.allowed_for_n) {
        throw new Error(q.message || "Not allowed to record this many FIR reports under your plan.");
      }

      const results: Array<{
        blob: Blob;
        filename: string;
        byteSize?: number;
        sizeWarning?: string;
      }> = new Array(n);

      let completed = 0;

      const updateProgress = (justFinishedMs: number | null) => {
        completed += 1;
        if (justFinishedMs != null && justFinishedMs > 0) {
          const arr = pdfDurationsRef.current;
          arr.push(justFinishedMs);
          if (arr.length > 8) arr.shift();
        }
        const remaining = n - completed;
        let etaSec: number | null = null;
        if (remaining > 0 && pdfDurationsRef.current.length) {
          const avg = pdfDurationsRef.current.reduce((a, b) => a + b, 0) / pdfDurationsRef.current.length;
          etaSec = Math.max(0, Math.round((avg * remaining) / 1000));
        } else if (remaining === 0) {
          etaSec = 0;
        }
        const pct = n ? Math.round((completed / n) * 100) : 100;
        setZipProgress({
          current: completed,
          total: n,
          label: `Generating PDF ${completed}/${n}`,
          etaSec,
          pct,
        });
      };

      setZipProgress({
        current: 0,
        total: n,
        label: `Generating PDF 0/${n}`,
        etaSec: null,
        pct: 0,
      });

      async function runOne(i: number) {
        const f = iframeRefs.current[i];
        if (!f?.contentWindow) throw new Error(`Report ${i + 1} is not ready for PDF export.`);
        const preRect = f.getBoundingClientRect();
        const iframeH = Math.max(1, Math.round(preRect.height));
        const viewportTopPx = computeCaptureTopPx(previewsSectionRef.current, iframeH);
        const restoreCaptureLayout = await prepareIframeForPdfCapture(f, viewportTopPx);
        try {
          let api: FirPreviewApi | null = null;
          try {
            api = (f.contentWindow as Window & { FIR_PREVIEW_API?: FirPreviewApi }).FIR_PREVIEW_API ?? null;
          } catch {
            api = null;
          }

          const runDirect = async () => {
            const gen = api!.generatePdfBlob!;
            /* generatePdfBlob already runs firWaitForAssets — do not wait here (main branch also did both = 2× wait). */
            const t0 = performance.now();
            const result = await gen();
            const dt = performance.now() - t0;
            return { result, dt };
          };

          const runViaPostMessage = async () => {
            const requestId = crypto.randomUUID();
            const origin = firIframeTargetOrigin(f);
            const t0 = performance.now();
            let timeoutId: ReturnType<typeof window.setTimeout> | undefined;
            const result = await new Promise<{
              blob: Blob;
              filename: string;
              byteSize?: number;
              sizeWarning?: string;
            }>((resolve, reject) => {
              const handler = (ev: MessageEvent) => {
                const d = ev.data;
                if (!d || d.source !== "fir-saas-fir-preview" || d.type !== "pdfBlobResult" || d.requestId !== requestId) {
                  return;
                }
                if (timeoutId !== undefined) window.clearTimeout(timeoutId);
                window.removeEventListener("message", handler);
                if (!d.ok) reject(new Error(d.error || "PDF generation failed"));
                else if (!d.blob) reject(new Error("No PDF blob returned"));
                else
                  resolve({
                    blob: d.blob as Blob,
                    filename: String(d.filename || `FIR_${i + 1}.pdf`),
                    byteSize: d.byteSize,
                    sizeWarning: d.sizeWarning,
                  });
              };
              window.addEventListener("message", handler);
              timeoutId = window.setTimeout(() => {
                window.removeEventListener("message", handler);
                reject(
                  new Error(
                    `Timed out waiting for PDF ${i + 1} (${Math.round(FIR_PDF_POSTMESSAGE_TIMEOUT_MS / 1000)}s). Try reloading or fewer rows.`,
                  ),
                );
              }, FIR_PDF_POSTMESSAGE_TIMEOUT_MS);
              f!.contentWindow!.postMessage(
                { source: "fir-saas-fir-preview-parent", type: "generatePdf", requestId },
                origin,
              );
            });
            const dt = performance.now() - t0;
            return { result, dt };
          };

          let result: {
            blob: Blob;
            filename: string;
            byteSize?: number;
            sizeWarning?: string;
          };
          let dt: number;
          if (api?.generatePdfBlob) {
            try {
              const out = await runDirect();
              result = out.result;
              dt = out.dt;
            } catch {
              const out = await runViaPostMessage();
              result = out.result;
              dt = out.dt;
            }
          } else {
            const out = await runViaPostMessage();
            result = out.result;
            dt = out.dt;
          }
          results[i] = result;
          updateProgress(dt);
        } finally {
          restoreCaptureLayout();
        }
      }

      for (let i = 0; i < n; i++) {
        await runOne(i);
      }

      const zip = new JSZip();
      for (let i = 0; i < n; i++) {
        const result = results[i];
        if (!result?.blob) throw new Error(`Report ${i + 1} produced no PDF data.`);
        const name = (result.filename || `FIR_${i + 1}.pdf`).replace(/[/\\]/g, "_");
        zip.file(name, result.blob);
      }

      const blob = await zip.generateAsync({
        type: "blob",
        compression: "DEFLATE",
        compressionOptions: { level: 1 },
      });
      const stamp = (data.current_date || "batch").replace(/\W+/g, "_");
      const zipName = `FIR_reports_${stamp}.zip`;
      lastZipOfferRef.current = { blob, filename: zipName };
      setZipSaveHint(true);
      triggerBlobDownload(blob, zipName);

      try {
        await workspaceFetch<RecordReportsRes>("/api/app/inspection/record-reports", {
          method: "POST",
          body: JSON.stringify({ rows: data.rows, source_file: st?.filename ?? null }),
        });
      } catch (recErr) {
        setBatchErr(
          `${recErr instanceof Error ? recErr.message : "Failed to log FIR usage"}. The ZIP file was still downloaded; contact support if billing did not update.`,
        );
        return;
      }
      try {
        const q2 = await fetchFirQuotaUsingIntelPreview(data.rows, st?.filename);
        setFirQuota(q2);
      } catch {
        setFirQuota(null);
      }
      setBatchMsg("ZIP ready — check your downloads folder.");
    } catch (e) {
      setZipSaveHint(false);
      lastZipOfferRef.current = null;
      setBatchErr(e instanceof Error ? e.message : "ZIP build failed");
    } finally {
      setZipping(false);
      setZipProgress(null);
    }
  }, [data, st?.filename]);

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

  if (err) {
    return <p className="text-red-600">{err}</p>;
  }
  if (!data) {
    return <p className="text-slate-600">Loading…</p>;
  }

  const cust = data.customer;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
      {zipping && (
        <div
          className="pointer-events-none fixed inset-0 z-[150] bg-slate-100"
          aria-hidden
        />
      )}

      <div className="relative z-[220] isolate space-y-5">
        <header className="space-y-1.5">
          <h1 className="text-xl font-semibold tracking-tight text-slate-900">Inspection results</h1>
          {cust && (
            <p className="text-sm text-slate-600">
              Vendor: <span className="font-mono">{cust.vendor_code}</span> — {cust.name}
            </p>
          )}
        </header>

        <section className="rounded-xl border border-slate-200 bg-slate-50 p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-800">Batch FIR tools</h2>
          {firQuota && !firQuota.allowed_for_n && firQuota.message && (
            <p className="mt-3 text-sm text-amber-800">{firQuota.message}</p>
          )}
          {firQuota && firQuota.allowed_for_n && firQuota.usage_limit != null && (
            <p className="mt-3 text-xs text-slate-600">
              This month: {firQuota.usage_this_month} / {firQuota.usage_limit} reports
              {firQuota.would_remain_after_n != null ? ` · after this ZIP: ${firQuota.would_remain_after_n} left` : ""}
            </p>
          )}
          <p className="mt-3 text-sm text-slate-600">
            Run <strong>Auto-fill</strong>, then <strong>Download ZIP</strong>. Use <strong>Preview FIR</strong> to open one
            report in a new tab.
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button
              type="button"
              disabled={!embedsReady || zipping}
              className="rounded-lg px-4 py-2.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-400"
              style={{ backgroundColor: embedsReady && !zipping ? "#17a2b8" : undefined }}
              onClick={runAutofillAll}
            >
              Auto-fill all measured values
            </button>
            <button
              type="button"
              disabled={!autofillApplied || zipping || (firQuota != null && !firQuota.allowed_for_n)}
              className="rounded-lg bg-green-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-green-700 disabled:cursor-not-allowed disabled:bg-slate-400"
              aria-busy={zipping}
              onClick={() => void downloadAllZip()}
            >
              {zipping ? "Building ZIP…" : "Download all reports as ZIP"}
            </button>
          </div>
          {zipProgress && (
            <div
              className="mt-5 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm"
              role="status"
              aria-live="polite"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-700">
                <span className="font-medium">{zipProgress.label}</span>
                {zipProgress.etaSec != null && zipProgress.current < zipProgress.total ? (
                  <span className="text-slate-600">About {zipProgress.etaSec}s remaining</span>
                ) : null}
              </div>
              <div className="mt-3 h-2.5 w-full overflow-hidden rounded-full bg-slate-200">
                <div
                  className="h-full rounded-full bg-green-600 transition-[width] duration-200"
                  style={{ width: `${zipProgress.pct}%` }}
                />
              </div>
            </div>
          )}
          {!embedsReady && !embedWaitTimedOut && (
            <p className="mt-4 text-xs text-amber-800">Loading FIR previews below…</p>
          )}
          {embedWaitTimedOut && !embedsReady && (
            <p className="mt-4 text-xs leading-relaxed text-red-700">
              Some previews did not become ready (invalid part data or network). You can still use <strong>Preview FIR</strong>{" "}
              per row.
            </p>
          )}
          {embedsReady && !autofillApplied && (
            <p className="mt-4 text-xs text-slate-600">
              Next: <strong>Auto-fill</strong>, then <strong>Download ZIP</strong>.
            </p>
          )}
          {batchMsg && <p className="mt-4 text-sm text-green-700">{batchMsg}</p>}
          {batchErr && <p className="mt-4 text-sm text-red-600">{batchErr}</p>}
          {zipSaveHint && (
            <p className="mt-4 text-xs text-slate-600">
              <button
                type="button"
                className="font-medium text-blue-700 underline"
                onClick={() => {
                  const o = lastZipOfferRef.current;
                  if (o) triggerBlobDownload(o.blob, o.filename);
                }}
              >
                Save the ZIP again
              </button>
              {" "}if it didn&apos;t download.
            </p>
          )}
        </section>

        <section
          className={`overflow-hidden rounded-xl border border-slate-200 bg-white ${
            zipping ? "shadow-md ring-2 ring-green-500/15" : ""
          }`}
        >
          {zipping && (
            <div className="flex items-center justify-between gap-3 border-b border-slate-100 bg-gradient-to-r from-slate-50 via-white to-slate-50 px-4 py-3">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-600">
                Parts in this batch
              </span>
              <span className="font-mono text-xs tabular-nums text-slate-500">
                {zipProgress ? `PDF ${zipProgress.current}/${zipProgress.total}` : "Starting…"}
              </span>
            </div>
          )}
          <div className="overflow-x-auto">
            <table className="min-w-full border-collapse text-sm">
              <thead>
                <tr className="bg-slate-100 text-slate-800">
                  <th className="border border-slate-200 px-3 py-2.5 text-left text-xs font-semibold">
                    Part Number
                  </th>
                  <th className="border border-slate-200 px-3 py-2.5 text-left text-xs font-semibold">Description</th>
                  <th className="border border-slate-200 px-3 py-2.5 text-left text-xs font-semibold">Draw Rev</th>
                  <th className="border border-slate-200 px-3 py-2.5 text-left text-xs font-semibold">Qty</th>
                  <th className="border border-slate-200 px-3 py-2.5 text-left text-xs font-semibold">Invoice</th>
                  <th className="border border-slate-200 px-3 py-2.5 text-left text-xs font-semibold">Sample</th>
                  <th className="border border-slate-200 px-3 py-2.5 text-left text-xs font-semibold">Params</th>
                  <th className="border border-slate-200 px-3 py-2.5 text-left text-xs font-semibold">FIR</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r, i) => (
                  <tr key={i} className={zipping && i % 2 === 1 ? "bg-slate-50/90" : zipping ? "bg-white" : ""}>
                    <td className="border border-slate-200 px-3 py-2">{String(r["Part Number"] ?? "")}</td>
                    <td className="border border-slate-200 px-3 py-2">{String(r["Description"] ?? "")}</td>
                    <td className="border border-slate-200 px-3 py-2">{String(r.draw_rev ?? "")}</td>
                    <td className="border border-slate-200 px-3 py-2">{String(r["Quantity"] ?? "")}</td>
                    <td className="border border-slate-200 px-3 py-2">{String(r["Invoice Number"] ?? "")}</td>
                    <td className="border border-slate-200 px-3 py-2">{String(r.sample_size ?? "")}</td>
                    <td className="border border-slate-200 px-3 py-2">{String(r.num_params ?? "")}</td>
                    <td className="border border-slate-200 px-3 py-2">
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
        </section>
      </div>

      <div ref={previewsSectionRef} className="mt-8 border-t border-slate-200 pt-6">
        <h2 className="text-lg font-semibold text-slate-900">Live FIR previews</h2>
        <p className="mt-2 text-sm text-slate-600">Previews update when you auto-fill; they are used to build the ZIP.</p>
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
                  loading="eager"
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
