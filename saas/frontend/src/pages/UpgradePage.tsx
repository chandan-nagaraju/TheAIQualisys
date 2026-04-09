import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { apiFetch } from "../api";
import { useTheme } from "../theme/ThemeContext";

type UpgradeInfo = { upi_id: string; whatsapp_url: string; message: string };
type PlanInfo = { plan_type: string; name: string; price_inr: number };

type BillingCycle = "monthly" | "annual";

export default function UpgradePage() {
  const loc = useLocation();
  const [info, setInfo] = useState<UpgradeInfo | null>(null);
  const [plans, setPlans] = useState<PlanInfo[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [billingCycle, setBillingCycle] = useState<BillingCycle>("monthly");
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
    const q = new URLSearchParams(loc.search);
    const b = (q.get("billing") || "").toLowerCase();
    if (b === "annual" || b === "yearly" || b === "1") {
      setBillingCycle("annual");
    }
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

  const isAnnual = billingCycle === "annual";

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
        ? "rounded-xl border border-slate-200 bg-slate-100/80 p-1"
        : theme === "grey"
          ? "rounded-xl border border-zinc-300 bg-zinc-200/80 p-1"
          : "rounded-xl border border-slate-600 bg-slate-800/80 p-1",
    toggleActive: theme === "dark" ? "bg-slate-700 text-white shadow" : "bg-white text-slate-900 shadow",
    toggleIdle:
      theme === "dark" ? "text-slate-400 hover:text-slate-200" : "text-slate-600 hover:text-slate-900",
  };

  const selectedPlanText = selected
    ? `${selected.planName}${selected.planType ? ` (${selected.planType})` : ""}`
    : null;
  const selectedAmountText = selected?.price != null ? `₹${selected.price.toLocaleString("en-IN")}/month` : null;
  const annualTotalText =
    selected?.price != null ? `₹${(selected.price * 11).toLocaleString("en-IN")}` : null;

  const whatsappHref = useMemo(() => {
    if (!info) return "";
    try {
      const u = new URL(info.whatsapp_url);
      if (!selected) {
        if (isAnnual) {
          u.searchParams.set(
            "text",
            [
              "Hi — I'm interested in TheAIQualisys FIR annual billing: pay for 11 months, get 12 months on the same plan limits.",
              `UPI ID: ${info.upi_id}.`,
              "Please confirm the annual total and next steps after I share the payment screenshot.",
            ].join(" "),
          );
        }
        return u.toString();
      }
      const annualBit =
        isAnnual && selected.price != null
          ? ` Billing: annual prepay ₹${selected.price}/month × 11 = ₹${selected.price * 11} for 12 months (same usage caps).`
          : isAnnual
            ? " Billing: annual prepay (11 months for 12 months on this plan)."
            : selected.price != null
              ? ` Billing: monthly ₹${selected.price}/month.`
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
  }, [info, selected, isAnnual]);

  return (
    <div className={`mx-auto w-full max-w-3xl rounded-2xl border p-5 shadow-sm sm:p-7 ${t.card}`}>
      <h1 className={`text-2xl font-semibold sm:text-3xl ${t.title}`}>Upgrade (manual payment)</h1>
      <p className={`mt-2 text-sm leading-relaxed sm:text-base ${t.lead}`}>
        Pay via UPI to the ID below, then send the screenshot on WhatsApp; our admin activates your subscription.
      </p>

      <div className={`mt-6 rounded-xl border p-4 sm:p-5 ${t.modulesBox}`}>
        <h2 className={`text-base font-semibold sm:text-lg ${t.modulesHeading}`}>Your modules &amp; pricing</h2>
        <p className={`mt-2 text-sm leading-relaxed ${t.modulesBody}`}>
          <strong className={theme === "dark" ? "text-slate-100" : "text-slate-800"}>FIR Automation</strong> — usage-based
          monthly plans (invoice + FIR report caps). Pick a plan on the pricing page, then return here to complete payment.
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
              <p className={`mt-1 text-sm ${t.selectedText}`}>Base rate from pricing: {selectedAmountText}</p>

              <p className={`mt-4 text-xs font-semibold uppercase tracking-wide ${t.selectedTitle}`}>Billing</p>
              <div className={`mt-2 flex max-w-md rounded-xl ${t.toggleWrap}`}>
                <button
                  type="button"
                  onClick={() => setBillingCycle("monthly")}
                  className={`flex-1 rounded-lg px-3 py-2.5 text-sm font-semibold transition ${
                    billingCycle === "monthly" ? t.toggleActive : t.toggleIdle
                  }`}
                >
                  Monthly
                </button>
                <button
                  type="button"
                  onClick={() => setBillingCycle("annual")}
                  className={`flex-1 rounded-lg px-3 py-2.5 text-sm font-semibold transition ${
                    billingCycle === "annual" ? t.toggleActive : t.toggleIdle
                  }`}
                >
                  Annual (11 mo. for 12)
                </button>
              </div>

              <div className="mt-4 rounded-lg border border-sky-200/60 bg-white/50 px-3 py-3 text-sm dark:border-sky-800/50 dark:bg-slate-900/40">
                {isAnnual ? (
                  <>
                    <p className="font-semibold text-slate-900 dark:text-slate-100">
                      Pay once: <strong>{annualTotalText}</strong>
                    </p>
                    <p className="mt-1 text-slate-600 dark:text-slate-400">
                      ₹{selected.price.toLocaleString("en-IN")}/month × 11 = {annualTotalText} — covers <strong>12 months</strong>{" "}
                      on the same usage caps.
                    </p>
                  </>
                ) : (
                  <>
                    <p className="font-semibold text-slate-900 dark:text-slate-100">
                      Pay each month: <strong>{selectedAmountText}</strong>
                    </p>
                    <p className="mt-1 text-slate-600 dark:text-slate-400">Same published monthly rate as on the pricing page.</p>
                  </>
                )}
              </div>
            </div>
          )}

          {selected && selected.price == null && (
            <div className={`rounded-xl border p-4 sm:p-5 ${t.selectedBox}`}>
              <p className={`text-sm ${t.selectedText}`}>Plan: {selectedPlanText}. Open pricing to see the rate for this plan.</p>
            </div>
          )}

          <div className={`rounded-xl border p-4 sm:p-5 ${t.upiBox}`}>
            <p className={`text-xs uppercase tracking-wide ${t.upiLabel}`}>UPI ID</p>
            <p className={`mt-1 break-all font-mono text-base sm:text-lg ${t.upiValue}`}>{info.upi_id}</p>
            <p className={`mt-3 text-sm ${t.msg}`}>
              In your UPI app, send{" "}
              {selected?.price != null ? (
                isAnnual ? (
                  <strong>{annualTotalText}</strong>
                ) : (
                  <strong>₹{selected.price.toLocaleString("en-IN")}</strong>
                )
              ) : (
                "the amount"
              )}{" "}
              {selected?.price != null && !isAnnual ? "for this month’s subscription" : selected?.price != null && isAnnual ? "for the annual prepay" : ""}{" "}
              to this ID, then share the screenshot on WhatsApp.
            </p>
          </div>

          <p className={`text-sm sm:text-base ${t.msg}`}>
            {selected
              ? `You chose ${selectedPlanText}. Use WhatsApp below — your message includes this plan and billing choice.`
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
