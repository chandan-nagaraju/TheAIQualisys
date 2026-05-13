import { useEffect, useMemo, useState } from "react";
import QRCode from "qrcode";
import { apiFetch } from "../api";
import { useTheme } from "../theme/ThemeContext";

type UpgradeInfo = { upi_id: string; whatsapp_url: string; message: string };
type PlanInfo = { plan_type: string; name: string; price_inr: number };

const QR_REFRESH_MS = 60_000;

const BILLING_OPTIONS = [
  { id: "1m" as const, label: "Month" },
  { id: "3m" as const, label: "Quarterly" },
  { id: "6m" as const, label: "Half yearly" },
  { id: "12m" as const, label: "Yearly" },
];

type BillingId = (typeof BILLING_OPTIONS)[number]["id"];

function isEnterprisePlan(planType: string, planName: string): boolean {
  const t = planType.trim().toLowerCase();
  const n = planName.trim().toLowerCase();
  return t === "enterprise" || n.includes("enterprise");
}

/**
 * Total INR for UPI. Enterprise: half-yearly = round(6m − m/2), yearly = 11×.
 * Basic / Pro / other: half-yearly = 6×, yearly = 11×.
 */
function billingTotalInr(monthly: number, id: BillingId, enterprise: boolean): number {
  switch (id) {
    case "1m":
      return monthly;
    case "3m":
      return monthly * 3;
    case "6m":
      return enterprise ? Math.round(monthly * 6 - monthly / 2) : monthly * 6;
    case "12m":
      return monthly * 11;
    default:
      return monthly;
  }
}

export default function UpgradePage() {
  const [info, setInfo] = useState<UpgradeInfo | null>(null);
  const [plans, setPlans] = useState<PlanInfo[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [billingSelection, setBillingSelection] = useState<BillingId | null>(null);
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

  const enterprisePricing = useMemo(
    () => (selected ? isEnterprisePlan(selected.planType, selected.planName) : false),
    [selected],
  );

  const payAmount = useMemo(() => {
    if (!billingSelection || selected?.price == null) return null;
    return billingTotalInr(selected.price, billingSelection, enterprisePricing);
  }, [selected?.price, billingSelection, enterprisePricing]);

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
    if (!billingSelection) return;
    const id = window.setInterval(() => setQrTick((n) => n + 1), QR_REFRESH_MS);
    return () => window.clearInterval(id);
  }, [billingSelection]);

  useEffect(() => {
    if (!billingSelection) return;
    setSecondsToRefresh(QR_REFRESH_MS / 1000);
    const id = window.setInterval(() => {
      setSecondsToRefresh((s) => (s <= 1 ? QR_REFRESH_MS / 1000 : s - 1));
    }, 1000);
    return () => window.clearInterval(id);
  }, [qrTick, billingSelection]);

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
    payBtnOn: "border-brand-700 bg-brand-600 text-white shadow-md ring-2 ring-brand-400/60",
    payBtnOff:
      theme === "dark"
        ? "border-slate-600 bg-brand-700/90 text-white hover:bg-brand-600"
        : "border-brand-600 bg-brand-600 text-white hover:bg-brand-500",
  };

  const selectedPlanText = selected
    ? `${selected.planName}${selected.planType ? ` (${selected.planType})` : ""}`
    : null;
  const listPriceLine =
    selected?.price != null ? `List price: ₹${selected.price}/month — choose how you want to pay.` : null;
  const billingLabel = billingSelection
    ? (BILLING_OPTIONS.find((o) => o.id === billingSelection)?.label ?? "")
    : "";

  const whatsappHref = useMemo(() => {
    if (!info || !billingSelection) return "";
    const tier = enterprisePricing ? "Enterprise tier pricing" : "Standard tier pricing";
    const periodLine =
      payAmount != null ? `Billing: ${billingLabel} (${tier}). Total due: ₹${payAmount}.` : "";
    if (!selected) return info.whatsapp_url;
    try {
      const u = new URL(info.whatsapp_url);
      const msgParts = [
        `I have chosen the ${selected.planName} plan${selected.planType ? ` (${selected.planType})` : ""}.`,
        periodLine,
        listPriceLine ? `${listPriceLine}` : "",
        `I will pay to UPI: ${info.upi_id}.`,
        "Please share activation confirmation after payment screenshot.",
      ].filter(Boolean);
      u.searchParams.set("text", msgParts.join(" "));
      return u.toString();
    } catch {
      return info.whatsapp_url;
    }
  }, [info, selected, payAmount, billingLabel, listPriceLine, billingSelection, enterprisePricing]);

  const upiPayload = useMemo(() => {
    if (!info || !billingSelection || payAmount == null) return "";
    const q = new URLSearchParams();
    q.set("pa", info.upi_id);
    q.set("pn", "TheAIQualisys");
    q.set("cu", "INR");
    q.set("am", String(payAmount));
    const period = BILLING_OPTIONS.find((o) => o.id === billingSelection);
    const periodPart = period ? period.label.replace(/\s+/g, "") : billingSelection;
    if (selected?.planName) {
      q.set(
        "tn",
        `Sub ${selected.planName}${selected.planType ? ` (${selected.planType})` : ""} ${periodPart} #${qrTick}-${Date.now()}`,
      );
    } else {
      q.set("tn", `Subscription ${periodPart} #${qrTick}-${Date.now()}`);
    }
    return `upi://pay?${q.toString()}`;
  }, [info, selected, payAmount, billingSelection, qrTick]);

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
        Choose <strong className="font-semibold text-slate-700 dark:text-slate-200">Month</strong>,{" "}
        <strong className="font-semibold text-slate-700 dark:text-slate-200">Quarterly</strong>,{" "}
        <strong className="font-semibold text-slate-700 dark:text-slate-200">Half yearly</strong>, or{" "}
        <strong className="font-semibold text-slate-700 dark:text-slate-200">Yearly</strong> below. Your UPI QR and
        payment details appear only after you choose. Then pay and send the screenshot on WhatsApp.
      </p>
      {err && <p className={`mt-4 text-sm ${t.err}`}>{err}</p>}
      {info && (
        <div className="mt-6 space-y-4 sm:mt-8">
          {billingSelection && (
            <div className="rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-900">
              QR payment — amount matches your billing choice; QR refreshes every {QR_REFRESH_MS / 1000} seconds
            </div>
          )}

          {selected && (
            <div className={`rounded-xl border p-4 sm:p-5 ${t.selectedBox}`}>
              <p className={`text-xs uppercase tracking-wide ${t.selectedTitle}`}>Selected plan</p>
              <p className={`mt-1 text-base font-semibold sm:text-lg ${t.selectedText}`}>{selectedPlanText}</p>
              {listPriceLine && <p className={`mt-1 text-sm ${t.selectedText}`}>{listPriceLine}</p>}
              {enterprisePricing && (
                <p className={`mt-2 text-xs font-medium text-amber-800 dark:text-amber-200`}>
                  Enterprise billing — special half-yearly and yearly totals apply.
                </p>
              )}
            </div>
          )}

          {selected?.price != null && (
            <div className={`rounded-xl border p-4 sm:p-5 ${t.upiBox}`}>
              <p className={`text-xs font-semibold uppercase tracking-wide ${t.upiLabel}`}>How do you want to pay?</p>
              <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                {BILLING_OPTIONS.map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => setBillingSelection(opt.id)}
                    className={`rounded-xl border-2 px-3 py-5 text-center text-sm font-semibold transition sm:py-6 sm:text-base ${
                      billingSelection === opt.id ? t.payBtnOn : t.payBtnOff
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
              <p className={`mt-4 text-center text-xs ${t.msg}`}>
                Tap <strong className="font-medium">Month</strong>, <strong className="font-medium">Quarterly</strong>,{" "}
                <strong className="font-medium">Half yearly</strong>, or <strong className="font-medium">Yearly</strong>{" "}
                to show your UPI QR and payment details.
              </p>
            </div>
          )}

          {billingSelection && payAmount != null && (
            <div
              className={`rounded-xl border px-4 py-3 text-center sm:px-5 sm:py-4 ${
                theme === "dark" ? "border-slate-600 bg-slate-800/50" : "border-slate-200 bg-slate-100/80"
              }`}
            >
              <p className={`text-xs uppercase tracking-wide ${t.upiLabel}`}>Amount to pay ({billingLabel})</p>
              <p className={`mt-1 text-2xl font-bold ${t.title}`}>₹{payAmount}</p>
            </div>
          )}

          {billingSelection && (
            <>
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
                      QR image not available on this device/browser yet. Use the button below to open the UPI app
                      directly.
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
            </>
          )}

          <p className={`text-sm sm:text-base ${t.msg}`}>
            {billingSelection && selected
              ? `You have chosen ${selectedPlanText} — ${billingLabel}. Send money to this UPI ID and share payment screenshot on the WhatsApp number below.`
              : selected
                ? listPriceLine || "Select a billing period above to generate your payment QR."
                : info.message}
          </p>
          {billingSelection ? (
            <a
              href={whatsappHref}
              target="_blank"
              rel="noreferrer"
              className="inline-flex min-h-11 w-full items-center justify-center rounded-lg bg-emerald-600 px-4 py-3 text-sm font-semibold text-white hover:bg-emerald-500 sm:text-base"
            >
              Open WhatsApp with message
            </a>
          ) : (
            <p className={`text-center text-sm ${t.msg}`}>
              Choose a billing period to enable WhatsApp with a prefilled message.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
