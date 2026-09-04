import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiFetch } from "../api";
import { useTheme } from "../theme/ThemeContext";
import {
  BILLING_OPTIONS,
  type PlanInfo,
  type UpgradeInfo,
  isEnterprisePlan,
  useSelectedPlan,
} from "./upgradeHelpers";

export default function UpgradePage() {
  const navigate = useNavigate();
  const [info, setInfo] = useState<UpgradeInfo | null>(null);
  const [plans, setPlans] = useState<PlanInfo[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const { theme } = useTheme();
  const selected = useSelectedPlan(plans);

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

  function goToPay(optId: (typeof BILLING_OPTIONS)[number]["id"]) {
    const q = new URLSearchParams(window.location.search);
    q.set("billing", optId);
    navigate(`/upgrade/pay?${q.toString()}`);
  }

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
    msg: theme === "dark" ? "text-slate-300" : "text-slate-600",
    selectedBox:
      theme === "light"
        ? "border-sky-200 bg-sky-50"
        : theme === "grey"
          ? "border-sky-300 bg-sky-100/60"
          : "border-sky-700/40 bg-sky-950/30",
    selectedTitle: theme === "dark" ? "text-sky-200" : "text-sky-900",
    selectedText: theme === "dark" ? "text-slate-200" : "text-slate-700",
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

  const enterprisePricing = useMemo(() => {
    if (!selected) return false;
    return isEnterprisePlan(selected.planType, selected.planName);
  }, [selected]);

  return (
    <div className={`mx-auto w-full max-w-3xl rounded-2xl border p-5 shadow-sm sm:p-7 ${t.card}`}>
      <h1 className={`text-2xl font-semibold sm:text-3xl ${t.title}`}>Upgrade (manual payment)</h1>
      <p className={`mt-2 text-sm leading-relaxed sm:text-base ${t.lead}`}>
        Choose <strong className="font-semibold text-slate-700 dark:text-slate-200">Month</strong>,{" "}
        <strong className="font-semibold text-slate-700 dark:text-slate-200">Quarterly</strong>,{" "}
        <strong className="font-semibold text-slate-700 dark:text-slate-200">Half yearly</strong>, or{" "}
        <strong className="font-semibold text-slate-700 dark:text-slate-200">Yearly</strong> below. You will go to a
        dedicated payment page with your UPI QR centered on screen (no scrolling needed to scan). Then pay and send the
        screenshot on WhatsApp.
      </p>
      {err && <p className={`mt-4 text-sm ${t.err}`}>{err}</p>}
      {info && (
        <div className="mt-6 space-y-4 sm:mt-8">
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
                    onClick={() => goToPay(opt.id)}
                    className={`rounded-xl border-2 px-3 py-5 text-center text-sm font-semibold transition sm:py-6 sm:text-base ${t.payBtnOff}`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
              <p className={`mt-4 text-center text-xs ${t.msg}`}>
                Tap a period to open the payment page with your QR and UPI details.
              </p>
            </div>
          )}

          <p className={`text-sm sm:text-base ${t.msg}`}>
            {selected
              ? listPriceLine || "Select a billing period to continue to payment."
              : info.message}
          </p>
        </div>
      )}
    </div>
  );
}
