import { useEffect, useMemo, useState } from "react";
import QRCode from "qrcode";
import { Link, Navigate, useLocation } from "react-router-dom";
import { apiFetch } from "../api";
import { useTheme } from "../theme/ThemeContext";
import {
  BILLING_OPTIONS,
  billingTotalInr,
  isEnterprisePlan,
  parseBillingId,
  QR_REFRESH_MS,
  type UpgradeInfo,
  type PlanInfo,
  useSelectedPlan,
} from "./upgradeHelpers";

export default function UpgradePayPage() {
  const location = useLocation();
  const billingParam = parseBillingId(new URLSearchParams(location.search).get("billing"));
  const [info, setInfo] = useState<UpgradeInfo | null>(null);
  const [plans, setPlans] = useState<PlanInfo[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [qrTick, setQrTick] = useState(0);
  const [qrDataUrl, setQrDataUrl] = useState<string>("");
  const [secondsToRefresh, setSecondsToRefresh] = useState(QR_REFRESH_MS / 1000);
  const { theme } = useTheme();

  const selected = useSelectedPlan(plans);
  const enterprisePricing = useMemo(
    () => (selected ? isEnterprisePlan(selected.planType, selected.planName) : false),
    [selected],
  );

  const payAmount = useMemo(() => {
    if (!billingParam || selected?.price == null) return null;
    return billingTotalInr(selected.price, billingParam, enterprisePricing);
  }, [selected?.price, billingParam, enterprisePricing]);

  const upgradeSearchStripped = useMemo(() => {
    const q = new URLSearchParams(location.search);
    q.delete("billing");
    const s = q.toString();
    return s ? `/upgrade?${s}` : "/upgrade";
  }, [location.search]);

  useEffect(() => {
    (async () => {
      try {
        const [upgradeInfo, planRows] = await Promise.all([
          apiFetch<UpgradeInfo>("/subscription/upgrade-info"),
          apiFetch<PlanInfo[]>("/subscription/plans"),
        ]);
        setInfo(upgradeInfo);
        setPlans(planRows);
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Failed to load");
      }
    })();
  }, []);

  useEffect(() => {
    if (!billingParam) return;
    const id = window.setInterval(() => setQrTick((n) => n + 1), QR_REFRESH_MS);
    return () => window.clearInterval(id);
  }, [billingParam]);

  useEffect(() => {
    if (!billingParam) return;
    setSecondsToRefresh(QR_REFRESH_MS / 1000);
    const id = window.setInterval(() => {
      setSecondsToRefresh((s) => (s <= 1 ? QR_REFRESH_MS / 1000 : s - 1));
    }, 1000);
    return () => window.clearInterval(id);
  }, [qrTick, billingParam]);

  const t = {
    wrap: theme === "light" ? "bg-slate-50" : theme === "grey" ? "bg-zinc-100" : "bg-slate-950",
    title: theme === "dark" ? "text-white" : "text-slate-900",
    sub: theme === "dark" ? "text-slate-400" : "text-slate-600",
    card:
      theme === "light"
        ? "border-slate-200 bg-white"
        : theme === "grey"
          ? "border-zinc-300 bg-white"
          : "border-slate-700 bg-slate-900/80",
    upiBox:
      theme === "light"
        ? "border-slate-200 bg-slate-50"
        : theme === "grey"
          ? "border-zinc-300 bg-zinc-50"
          : "border-slate-600 bg-slate-800/60",
    upiLabel: theme === "dark" ? "text-slate-400" : "text-slate-500",
    upiValue: theme === "dark" ? "text-slate-100" : "text-slate-900",
    err: theme === "dark" ? "text-red-400" : "text-red-600",
  };

  const selectedPlanText = selected
    ? `${selected.planName}${selected.planType ? ` (${selected.planType})` : ""}`
    : "";
  const listPriceLine =
    selected?.price != null ? `List price: ₹${selected.price}/month` : null;
  const billingLabel = billingParam
    ? (BILLING_OPTIONS.find((o) => o.id === billingParam)?.label ?? "")
    : "";

  const whatsappHref = useMemo(() => {
    if (!info || !billingParam) return "";
    const tier = enterprisePricing ? "Enterprise tier pricing" : "Standard tier pricing";
    const periodLine =
      payAmount != null ? `Billing: ${billingLabel} (${tier}). Total due: ₹${payAmount}.` : "";
    if (!selected) return info.whatsapp_url;
    try {
      const u = new URL(info.whatsapp_url);
      const msgParts = [
        `I have chosen the ${selected.planName} plan${selected.planType ? ` (${selected.planType})` : ""}.`,
        periodLine,
        listPriceLine ? `${listPriceLine}.` : "",
        `I will pay to UPI: ${info.upi_id}.`,
        "Please share activation confirmation after payment screenshot.",
      ].filter(Boolean);
      u.searchParams.set("text", msgParts.join(" "));
      return u.toString();
    } catch {
      return info.whatsapp_url;
    }
  }, [info, selected, payAmount, billingLabel, listPriceLine, billingParam, enterprisePricing]);

  const upiPayload = useMemo(() => {
    if (!info || !billingParam || payAmount == null) return "";
    const q = new URLSearchParams();
    q.set("pa", info.upi_id);
    q.set("pn", "TheAIQualisys");
    q.set("cu", "INR");
    q.set("am", String(payAmount));
    const period = BILLING_OPTIONS.find((o) => o.id === billingParam);
    const periodPart = period ? period.label.replace(/\s+/g, "") : billingParam;
    if (selected?.planName) {
      q.set(
        "tn",
        `Sub ${selected.planName}${selected.planType ? ` (${selected.planType})` : ""} ${periodPart} #${qrTick}-${Date.now()}`,
      );
    } else {
      q.set("tn", `Subscription ${periodPart} #${qrTick}-${Date.now()}`);
    }
    return `upi://pay?${q.toString()}`;
  }, [info, selected, payAmount, billingParam, qrTick]);

  const qrImageUrl = useMemo(() => {
    if (!upiPayload) return "";
    return `https://api.qrserver.com/v1/create-qr-code/?size=240x240&data=${encodeURIComponent(upiPayload)}`;
  }, [upiPayload]);

  useEffect(() => {
    let cancelled = false;
    if (!upiPayload) {
      setQrDataUrl("");
      return;
    }
    QRCode.toDataURL(upiPayload, {
      width: 240,
      margin: 1,
      errorCorrectionLevel: "M",
    })
      .then((url) => {
        if (!cancelled) setQrDataUrl(url);
      })
      .catch(() => {
        if (!cancelled) setQrDataUrl("");
      });
    return () => {
      cancelled = true;
    };
  }, [upiPayload]);

  if (!billingParam) {
    return <Navigate to={upgradeSearchStripped} replace />;
  }

  if (err) {
    return (
      <div className={`mx-auto max-w-lg rounded-2xl border p-6 ${t.card}`}>
        <p className={t.err}>{err}</p>
        <Link to={upgradeSearchStripped} className="mt-4 inline-block text-sm font-semibold text-brand-600">
          Back to upgrade
        </Link>
      </div>
    );
  }

  if (!info) {
    return (
      <div className={`flex min-h-[50vh] items-center justify-center ${t.wrap}`}>
        <p className={t.sub}>Loading payment…</p>
      </div>
    );
  }

  if (!selected || selected.price == null || payAmount == null) {
    return <Navigate to={upgradeSearchStripped} replace />;
  }

  return (
    <div
      className={`flex min-h-[calc(100dvh-7rem)] flex-col items-center justify-center px-3 py-4 sm:min-h-[calc(100dvh-8rem)] ${t.wrap}`}
    >
      <div className={`w-full max-w-sm rounded-2xl border px-4 py-5 shadow-sm sm:max-w-md sm:px-6 ${t.card}`}>
        <div className="text-center">
          <p className={`text-[11px] font-semibold uppercase tracking-wide ${t.upiLabel}`}>
            Pay · {billingLabel}
          </p>
          <p className={`mt-1 text-xl font-bold tabular-nums sm:text-2xl ${t.title}`}>₹{payAmount}</p>
          <p className={`mt-1 text-xs ${t.sub}`}>{selectedPlanText}</p>
        </div>

        <div className="mt-4 flex justify-center">
          {qrDataUrl || qrImageUrl ? (
            <img
              src={qrDataUrl || qrImageUrl}
              alt="UPI payment QR"
              className="h-44 w-44 max-h-[38vh] max-w-[38vh] rounded-lg border border-slate-300 bg-white p-1.5 sm:h-52 sm:w-52"
            />
          ) : (
            <div className="rounded-md border border-amber-300 bg-amber-50 px-2 py-2 text-center text-[11px] text-amber-900">
              Generating QR… If this persists, use &quot;Open in UPI app&quot; below.
            </div>
          )}
        </div>

        <p className={`mt-2 text-center text-[11px] ${t.sub}`}>
          New QR in ~{secondsToRefresh}s · {billingLabel} · ₹{payAmount}
        </p>

        <div className={`mt-3 rounded-lg border px-3 py-2 text-center ${t.upiBox}`}>
          <p className={`text-[10px] uppercase tracking-wide ${t.upiLabel}`}>UPI ID</p>
          <p className={`break-all font-mono text-xs ${t.upiValue}`}>{info.upi_id}</p>
        </div>

        <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:justify-center">
          {upiPayload ? (
            <a
              href={upiPayload}
              className="inline-flex min-h-10 flex-1 items-center justify-center rounded-lg border border-emerald-600 px-3 py-2 text-center text-sm font-semibold text-emerald-700 hover:bg-emerald-50"
            >
              Open in UPI app
            </a>
          ) : null}
          <a
            href={whatsappHref}
            target="_blank"
            rel="noreferrer"
            className="inline-flex min-h-10 flex-1 items-center justify-center rounded-lg bg-emerald-600 px-3 py-2 text-center text-sm font-semibold text-white hover:bg-emerald-500"
          >
            WhatsApp screenshot
          </a>
        </div>

        <p className={`mt-3 text-center text-xs leading-snug ${t.sub}`}>
          Pay with the QR or UPI app, then send your payment screenshot via WhatsApp.
        </p>

        <div className="mt-4 text-center">
          <Link
            to={upgradeSearchStripped}
            className="text-sm font-medium text-brand-600 underline hover:text-brand-500"
          >
            Change billing period
          </Link>
        </div>
      </div>
    </div>
  );
}
