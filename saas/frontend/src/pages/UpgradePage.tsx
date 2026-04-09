import { useEffect, useMemo, useState } from "react";
import QRCode from "qrcode";
import { Link, useLocation } from "react-router-dom";
import { apiFetch } from "../api";
import { useTheme } from "../theme/ThemeContext";

type UpgradeInfo = { upi_id: string; whatsapp_url: string; message: string };
type PlanInfo = { plan_type: string; name: string; price_inr: number };

type BillingChoice = "monthly" | "annual";

function fmtInr(n: number) {
  return `₹${n.toLocaleString("en-IN")}`;
}

export default function UpgradePage() {
  const loc = useLocation();
  const [info, setInfo] = useState<UpgradeInfo | null>(null);
  const [plans, setPlans] = useState<PlanInfo[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [billingChoice, setBillingChoice] = useState<BillingChoice | null>(null);
  const [qrTick, setQrTick] = useState(0);
  const [qrDataUrl, setQrDataUrl] = useState("");
  const { theme } = useTheme();

  const selected = useMemo(() => {
    const q = new URLSearchParams(loc.search);
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
  }, [plans, loc.search]);

  useEffect(() => {
    setBillingChoice(null);
  }, [loc.search]);

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
    const id = window.setInterval(() => setQrTick((n) => n + 1), 30_000);
    return () => window.clearInterval(id);
  }, []);

  const isAnnual = billingChoice === "annual";
  const showPayment = Boolean(selected?.price != null && billingChoice !== null);

  const upiPayload = useMemo(() => {
    if (!info || !selected?.price || !billingChoice) return "";
    const q = new URLSearchParams();
    q.set("pa", info.upi_id);
    q.set("pn", "TheAIQualisys");
    q.set("cu", "INR");
    const amount = isAnnual ? selected.price * 11 : selected.price;
    q.set("am", String(amount));
    const label = isAnnual ? "Annual FIR" : "FIR monthly";
    q.set("tn", `${label} ${selected.planName} #${Date.now()}`);
    return `upi://pay?${q.toString()}`;
  }, [info, selected, billingChoice, isAnnual, qrTick]);

  useEffect(() => {
    let cancelled = false;
    if (!showPayment || !upiPayload) {
      setQrDataUrl("");
      return;
    }
    QRCode.toDataURL(upiPayload, { width: 280, margin: 1, errorCorrectionLevel: "M" })
      .then((url) => {
        if (!cancelled) setQrDataUrl(url);
      })
      .catch(() => {
        if (!cancelled) setQrDataUrl("");
      });
    return () => {
      cancelled = true;
    };
  }, [showPayment, upiPayload]);

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
    modulesBox:
      theme === "light"
        ? "border-slate-200 bg-slate-50"
        : theme === "grey"
          ? "border-zinc-300 bg-zinc-100/90"
          : "border-slate-700 bg-slate-950/50",
    modulesHeading: theme === "dark" ? "text-white" : "text-slate-900",
    modulesBody: theme === "dark" ? "text-slate-300" : "text-slate-600",
    toggleWrap:
      theme === "light"
        ? "border border-slate-200 bg-slate-100/90"
        : theme === "grey"
          ? "border border-zinc-300 bg-zinc-200/90"
          : "border border-slate-600 bg-slate-800/90",
    toggleActive: theme === "dark" ? "bg-slate-700 text-white" : "bg-white text-slate-900 shadow-inner",
    toggleIdle:
      theme === "dark" ? "text-slate-400 hover:bg-slate-700/50 hover:text-slate-100" : "text-slate-600 hover:bg-white/70 hover:text-slate-900",
  };

  const selectedPlanText = selected
    ? `${selected.planName}${selected.planType ? ` (${selected.planType})` : ""}`
    : null;

  const annualTotal = selected?.price != null ? selected.price * 11 : null;
  const annualLine = annualTotal != null ? fmtInr(annualTotal) : null;

  const whatsappHref = useMemo(() => {
    if (!info || billingChoice === null || !selected) return "";
    try {
      const u = new URL(info.whatsapp_url);
      const annualBit =
        isAnnual && selected.price != null
          ? ` Pay: Year — ${fmtInr(selected.price)}/month × 11 = ${fmtInr(selected.price * 11)} for 12 months (same usage caps).`
          : isAnnual
            ? " Pay: Year — annual prepay (11 months for 12 months on this plan)."
            : selected.price != null
              ? ` Pay: Month — ${fmtInr(selected.price)}/month.`
              : "";
      const msgParts = [
        `I have chosen the ${selected.planName} plan${selected.planType ? ` (${selected.planType})` : ""}.`,
        annualBit,
        `I will pay to UPI: ${info.upi_id}.`,
        "Please share activation confirmation after payment screenshot.",
      ].filter(Boolean);
      u.searchParams.set("text", msgParts.join(" "));
      return u.toString();
    } catch {
      return info.whatsapp_url;
    }
  }, [info, selected, billingChoice, isAnnual]);

  const qrFallbackUrl = useMemo(() => {
    if (!upiPayload) return "";
    return `https://api.qrserver.com/v1/create-qr-code/?size=280x280&data=${encodeURIComponent(upiPayload)}`;
  }, [upiPayload]);

  return (
    <div className={`mx-auto w-full max-w-3xl rounded-2xl border p-5 shadow-sm sm:p-7 ${t.card}`}>
      <h1 className={`text-2xl font-semibold sm:text-3xl ${t.title}`}>Upgrade (manual payment)</h1>
      <p className={`mt-2 text-sm leading-relaxed sm:text-base ${t.lead}`}>
        Choose <strong>Month</strong> or <strong>Year</strong> below. Your UPI QR and payment details appear only after you
        choose. Then pay and send the screenshot on WhatsApp.
      </p>

      <div className={`mt-6 rounded-xl border p-4 sm:p-5 ${t.modulesBox}`}>
        <h2 className={`text-base font-semibold sm:text-lg ${t.modulesHeading}`}>Your modules &amp; pricing</h2>
        <p className={`mt-2 text-sm leading-relaxed ${t.modulesBody}`}>
          <strong className={theme === "dark" ? "text-slate-100" : "text-slate-800"}>FIR Automation</strong> — pick a plan
          on the pricing page, then select billing here.
        </p>
        <Link
          to="/workspace/pricing"
          className="mt-4 inline-flex min-h-11 items-center justify-center rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-700"
        >
          View FIR pricing &amp; plans
        </Link>
      </div>

      {err && <p className={`mt-4 text-sm ${t.err}`}>{err}</p>}
      {info && (
        <div className="mt-6 space-y-4 sm:mt-8">
          {selected && selected.price != null && (
            <div className={`rounded-xl border p-4 sm:p-5 ${t.selectedBox}`}>
              <p className={`text-xs uppercase tracking-wide ${t.selectedTitle}`}>Selected plan</p>
              <p className={`mt-1 text-base font-semibold sm:text-lg ${t.selectedText}`}>{selectedPlanText}</p>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                List price: {fmtInr(selected.price)}/month — choose how you want to pay.
              </p>

              <p className={`mt-4 text-xs font-semibold uppercase tracking-wide ${t.selectedTitle}`}>How do you want to pay?</p>
              <div className={`mt-2 grid max-w-lg grid-cols-2 overflow-hidden rounded-xl ${t.toggleWrap}`}>
                <button
                  type="button"
                  onClick={() => setBillingChoice("monthly")}
                  className={`border-r border-slate-300/80 px-3 py-3.5 text-center text-sm font-semibold transition dark:border-slate-600 ${
                    billingChoice === "monthly" ? t.toggleActive : t.toggleIdle
                  }`}
                >
                  Month
                </button>
                <button
                  type="button"
                  onClick={() => setBillingChoice("annual")}
                  className={`px-3 py-3.5 text-center text-sm font-semibold transition ${
                    billingChoice === "annual" ? t.toggleActive : t.toggleIdle
                  }`}
                >
                  Year
                </button>
              </div>

              {billingChoice !== null && (
                <div
                  className="mt-4 rounded-xl border border-sky-300/70 bg-white px-4 py-5 text-center dark:border-sky-700/50 dark:bg-slate-900/50"
                  role="status"
                  aria-live="polite"
                >
                  {isAnnual ? (
                    <>
                      <p className="text-xs font-semibold uppercase tracking-wide text-sky-800 dark:text-sky-300">
                        Amount to pay (year)
                      </p>
                      <p className="mt-2 text-3xl font-bold tracking-tight text-slate-900 dark:text-white">{annualLine}</p>
                      <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
                        {fmtInr(selected.price)}/month × 11 = {annualLine} — 12 months on the same caps
                      </p>
                    </>
                  ) : (
                    <>
                      <p className="text-xs font-semibold uppercase tracking-wide text-sky-800 dark:text-sky-300">
                        Amount to pay (month)
                      </p>
                      <p className="mt-2 text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
                        {fmtInr(selected.price)}
                      </p>
                      <p className="mt-1 text-base font-medium text-slate-600 dark:text-slate-300">per month</p>
                    </>
                  )}
                </div>
              )}

              {billingChoice === null && (
                <p className="mt-4 text-sm font-medium text-amber-800 dark:text-amber-200/90">
                  Tap <strong>Month</strong> or <strong>Year</strong> to show your UPI QR and payment details.
                </p>
              )}
            </div>
          )}

          {selected && selected.price == null && (
            <div className={`rounded-xl border p-4 sm:p-5 ${t.selectedBox}`}>
              <p className={`text-sm ${t.selectedText}`}>Plan: {selectedPlanText}. Open pricing to see the rate for this plan.</p>
            </div>
          )}

          {showPayment && selected?.price != null && (
            <>
              <div className="rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-900">
                QR payment mode enabled — amount matches your {isAnnual ? "annual (×11)" : "monthly"} choice
              </div>
              <div className={`rounded-xl border p-4 sm:p-5 ${t.upiBox}`}>
                <p className={`text-xs uppercase tracking-wide ${t.upiLabel}`}>UPI ID</p>
                <p className={`mt-1 break-all font-mono text-base sm:text-lg ${t.upiValue}`}>{info.upi_id}</p>
              </div>
              <div className={`rounded-xl border p-4 sm:p-5 ${t.upiBox}`}>
                <p className={`text-xs uppercase tracking-wide ${t.upiLabel}`}>Scan QR to pay</p>
                <div className="mt-3 flex flex-col items-center gap-3">
                  {qrDataUrl || qrFallbackUrl ? (
                    <img
                      src={qrDataUrl || qrFallbackUrl}
                      alt="UPI payment QR"
                      className="h-56 w-56 rounded-lg border border-slate-300 bg-white p-2"
                    />
                  ) : (
                    <div className="w-full rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                      Generating QR…
                    </div>
                  )}
                  <p className={`text-center text-xs ${t.msg}`}>
                    QR refreshes every 30 seconds. Amount:{" "}
                    <strong>{isAnnual ? annualLine : fmtInr(selected.price)}</strong>
                    {isAnnual ? " (year)" : " (month)"}.
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
                Pay using the QR or UPI app, then open WhatsApp with the prefilled message.
              </p>
              <a
                href={whatsappHref}
                target="_blank"
                rel="noreferrer"
                className="inline-flex min-h-11 w-full items-center justify-center rounded-lg bg-emerald-600 px-4 py-3 text-sm font-semibold text-white hover:bg-emerald-500 sm:text-base"
              >
                Open WhatsApp with message
              </a>
            </>
          )}
        </div>
      )}
    </div>
  );
}
