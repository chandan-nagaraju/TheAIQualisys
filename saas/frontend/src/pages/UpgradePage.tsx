import { useEffect, useMemo, useState } from "react";
import QRCode from "qrcode";
import { apiFetch } from "../api";
import { useTheme } from "../theme/ThemeContext";

type UpgradeInfo = { upi_id: string; whatsapp_url: string; message: string };
type PlanInfo = { plan_type: string; name: string; price_inr: number };

const QR_REFRESH_MS = 60_000;

const BILLING_OPTIONS = [
  { id: "1m" as const, label: "Monthly", months: 1 },
  { id: "3m" as const, label: "Quarterly", months: 3, sub: "3 × monthly" },
  { id: "6m" as const, label: "Half-yearly", months: 6, sub: "6 × monthly" },
  { id: "12m" as const, label: "Yearly", months: 12, sub: "12 × monthly" },
];

type BillingId = (typeof BILLING_OPTIONS)[number]["id"];

export default function UpgradePage() {
  const [info, setInfo] = useState<UpgradeInfo | null>(null);
  const [plans, setPlans] = useState<PlanInfo[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [billingPeriod, setBillingPeriod] = useState<BillingId>("1m");
  const [qrTick, setQrTick] = useState(0);
  const [qrDataUrl, setQrDataUrl] = useState<string>("");
  const [secondsToRefresh, setSecondsToRefresh] = useState(QR_REFRESH_MS / 1000);
  const { theme } = useTheme();
  const selected = useMemo(() => {
    const q = new URLSearchParams(window.location.search);
    const planName = (q.get("plan_name") || q.get("plan") || "").trim();
    const planType = (q.get("plan_type") || "").trim();
    const priceRaw = (
      q.get("price_inr") ||
      q.get("price_in") ||
      q.get("price") ||
      q.get("rate") ||
      ""
    ).trim();
    const price = /^\d+$/.test(priceRaw) ? Number(priceRaw) : null;
    const planTypeNorm = planType.toLowerCase();
    const planNameNorm = planName.toLowerCase();
    const matched = plans.find(
      (p) =>
        (planTypeNorm && p.plan_type.toLowerCase() === planTypeNorm) ||
        (planNameNorm && p.name.toLowerCase() === planNameNorm),
    );
    if (!planName && !planType && price == null && !matched) return null;
    return {
      planName: planName || matched?.name || "Selected plan",
      planType: planType || matched?.plan_type || "",
      price: price ?? matched?.price_inr ?? null,
    };
  }, [plans]);

  const months = useMemo(
    () => BILLING_OPTIONS.find((o) => o.id === billingPeriod)?.months ?? 1,
    [billingPeriod],
  );

  const payAmount = useMemo(() => {
    if (selected?.price == null) return null;
    return selected.price * months;
  }, [selected?.price, months]);

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
    const id = window.setInterval(() => setQrTick((n) => n + 1), QR_REFRESH_MS);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    setSecondsToRefresh(QR_REFRESH_MS / 1000);
    const id = window.setInterval(() => {
      setSecondsToRefresh((s) => (s <= 1 ? QR_REFRESH_MS / 1000 : s - 1));
    }, 1000);
    return () => window.clearInterval(id);
  }, [qrTick]);

  const t = {
    card:
      theme === "light"
        ? "border-slate-200 bg-white"
        : theme === "grey"
          ? "border-zinc-300 bg-zinc-50"
          : "border-slate-800 bg-slate-900/60",
    title: theme === "dark" ? "text-white" : "text-slate-900",
    lead: theme === "dark" ? "text-slate-300" : "text-slate-600",
    err: theme === "dark" ? "text-red-400" : "text-red-600",
    upiBox:
      theme === "light"
        ? "border-slate-200 bg-slate-50"
        : theme === "grey"
          ? "border-zinc-300 bg-zinc-100"
          : "border-slate-700 bg-slate-950/80",
    upiLabel: theme === "dark" ? "text-slate-400" : "text-slate-500",
    upiValue: theme === "dark" ? "text-slate-100" : "text-slate-900",
    msg: theme === "dark" ? "text-slate-300" : "text-slate-600",
    selectedBox:
      theme === "light"
        ? "border-sky-200 bg-sky-50"
        : theme === "grey"
          ? "border-sky-300 bg-sky-100/60"
          : "border-sky-700/40 bg-sky-950/30",
    selectedTitle: theme === "dark" ? "text-sky-200" : "text-sky-900",
    selectedText: theme === "dark" ? "text-slate-200" : "text-slate-700",
    periodBtnOn:
      theme === "dark"
        ? "border-brand-500 bg-brand-600/30 text-white ring-2 ring-brand-500/50"
        : "border-brand-500 bg-brand-50 text-brand-900 ring-2 ring-brand-400/40",
    periodBtnOff:
      theme === "dark"
        ? "border-slate-600 bg-slate-800/80 text-slate-200 hover:border-slate-500"
        : "border-slate-200 bg-white text-slate-800 hover:border-slate-300",
  };

  const selectedPlanText = selected
    ? `${selected.planName}${selected.planType ? ` (${selected.planType})` : ""}`
    : null;
  const listRateText = selected?.price != null ? `₹${selected.price}/month list price` : null;
  const billingLabel = BILLING_OPTIONS.find((o) => o.id === billingPeriod)?.label ?? "";

  const whatsappHref = useMemo(() => {
    if (!info) return "";
    const periodLine =
      payAmount != null && selected?.price != null
        ? `Billing: ${billingLabel} — ₹${selected.price}/mo × ${months} = ₹${payAmount} total.`
        : "";
    if (!selected) return info.whatsapp_url;
    try {
      const u = new URL(info.whatsapp_url);
      const msgParts = [
        `I have chosen the ${selected.planName} plan${selected.planType ? ` (${selected.planType})` : ""}.`,
        periodLine,
        listRateText ? `List rate: ${listRateText}.` : "",
        `I will pay to UPI: ${info.upi_id}.`,
        "Please share activation confirmation after payment screenshot.",
      ].filter(Boolean);
      u.searchParams.set("text", msgParts.join(" "));
      return u.toString();
    } catch {
      return info.whatsapp_url;
    }
  }, [info, selected, payAmount, months, billingLabel, listRateText]);

  const upiPayload = useMemo(() => {
    if (!info) return "";
    const q = new URLSearchParams();
    q.set("pa", info.upi_id);
    q.set("pn", "TheAIQualisys");
    q.set("cu", "INR");
    if (payAmount != null) q.set("am", String(payAmount));
    const period = BILLING_OPTIONS.find((o) => o.id === billingPeriod);
    const periodPart = period ? `${period.label} ${period.months}mo` : billingPeriod;
    if (selected?.planName) {
      q.set(
        "tn",
        `Sub ${selected.planName}${selected.planType ? ` (${selected.planType})` : ""} ${periodPart} #${qrTick}-${Date.now()}`,
      );
    } else {
      q.set("tn", `Subscription ${periodPart} #${qrTick}-${Date.now()}`);
    }
    return `upi://pay?${q.toString()}`;
  }, [info, selected, payAmount, billingPeriod, qrTick]);

  const qrImageUrl = useMemo(() => {
    if (!upiPayload) return "";
    return `https://api.qrserver.com/v1/create-qr-code/?size=280x280&data=${encodeURIComponent(upiPayload)}`;
  }, [upiPayload]);

  useEffect(() => {
    let cancelled = false;
    if (!upiPayload) {
      setQrDataUrl("");
      return;
    }
    QRCode.toDataURL(upiPayload, {
      width: 280,
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

  return (
    <div className={`mx-auto w-full max-w-3xl rounded-2xl border p-5 shadow-sm sm:p-7 ${t.card}`}>
      <h1 className={`text-2xl font-semibold sm:text-3xl ${t.title}`}>Upgrade (manual payment)</h1>
      <p className={`mt-2 text-sm leading-relaxed sm:text-base ${t.lead}`}>
        We use a simple UPI + WhatsApp flow. After you pay, send the screenshot on WhatsApp; our admin activates your
        subscription.
      </p>
      {err && <p className={`mt-4 text-sm ${t.err}`}>{err}</p>}
      {info && (
        <div className="mt-6 space-y-4 sm:mt-8">
          <div className="rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-900">
            QR payment mode enabled — amount matches your billing period; QR regenerates every {QR_REFRESH_MS / 1000}{" "}
            seconds
          </div>
          {selected && (
            <div className={`rounded-xl border p-4 sm:p-5 ${t.selectedBox}`}>
              <p className={`text-xs uppercase tracking-wide ${t.selectedTitle}`}>Selected plan</p>
              <p className={`mt-1 text-base font-semibold sm:text-lg ${t.selectedText}`}>{selectedPlanText}</p>
              {listRateText && (
                <p className={`mt-1 text-sm ${t.selectedText}`}>
                  {listRateText} — choose how you want to pay.
                </p>
              )}
            </div>
          )}

          {selected?.price != null && (
            <div className={`rounded-xl border p-4 sm:p-5 ${t.upiBox}`}>
              <p className={`text-xs uppercase tracking-wide ${t.upiLabel}`}>Billing period</p>
              <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                {BILLING_OPTIONS.map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => setBillingPeriod(opt.id)}
                    className={`rounded-lg border px-3 py-2.5 text-left text-sm font-medium transition ${
                      billingPeriod === opt.id ? t.periodBtnOn : t.periodBtnOff
                    }`}
                  >
                    <span className="block">{opt.label}</span>
                    <span className="mt-0.5 block text-xs font-normal opacity-80">{opt.sub}</span>
                    <span className="mt-1 block text-xs font-semibold">₹{selected.price * opt.months}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {payAmount != null && (
            <div
              className={`rounded-xl border px-4 py-3 text-center sm:px-5 sm:py-4 ${
                theme === "dark" ? "border-slate-600 bg-slate-800/50" : "border-slate-200 bg-slate-100/80"
              }`}
            >
              <p className={`text-xs uppercase tracking-wide ${t.upiLabel}`}>Amount to pay ({billingLabel})</p>
              <p className={`mt-1 text-2xl font-bold ${t.title}`}>₹{payAmount}</p>
              <p className={`mt-1 text-sm ${t.msg}`}>
                {months === 1 ? "per month" : `total for ${months} months (₹${selected?.price}/month)`}
              </p>
            </div>
          )}

          <div className={`rounded-xl border p-4 sm:p-5 ${t.upiBox}`}>
            <p className={`text-xs uppercase tracking-wide ${t.upiLabel}`}>UPI ID</p>
            <p className={`mt-1 break-all font-mono text-base sm:text-lg ${t.upiValue}`}>{info.upi_id}</p>
          </div>
          <div className={`rounded-xl border p-4 sm:p-5 ${t.upiBox}`}>
            <p className={`text-xs uppercase tracking-wide ${t.upiLabel}`}>Scan QR to pay</p>
            <div className="mt-3 flex flex-col items-center gap-3">
              {qrDataUrl || qrImageUrl ? (
                <img
                  src={qrDataUrl || qrImageUrl}
                  alt="UPI payment QR"
                  className="h-56 w-56 rounded-lg border border-slate-300 bg-white p-2"
                />
              ) : (
                <div className="w-full rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                  QR image not available on this device/browser yet. Use the button below to open the UPI app directly.
                </div>
              )}
              <p className={`text-xs ${t.msg}`}>
                New QR in ~{secondsToRefresh}s ({billingLabel}
                {payAmount != null ? ` · ₹${payAmount}` : ""})
              </p>
              {upiPayload ? (
                <a
                  href={upiPayload}
                  className="inline-flex min-h-10 items-center justify-center rounded-lg border border-emerald-600 px-4 py-2 text-sm font-semibold text-emerald-700 hover:bg-emerald-50"
                >
                  Open in UPI app
                </a>
              ) : null}
            </div>
          </div>
          <p className={`text-sm sm:text-base ${t.msg}`}>
            {selected
              ? `You have chosen ${selectedPlanText}${
                  payAmount != null
                    ? ` — ${billingLabel}, ₹${payAmount} total`
                    : listRateText
                      ? ` at ${listRateText}`
                      : ""
                }. Send money to this UPI ID and share payment screenshot on the WhatsApp number below.`
              : info.message}
          </p>
          <a
            href={whatsappHref}
            target="_blank"
            rel="noreferrer"
            className="inline-flex min-h-11 w-full items-center justify-center rounded-lg bg-emerald-600 px-4 py-3 text-sm font-semibold text-white hover:bg-emerald-500 sm:text-base"
          >
            Open WhatsApp with message
          </a>
        </div>
      )}
    </div>
  );
}
