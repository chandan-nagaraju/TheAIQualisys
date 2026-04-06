import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "../api";
import { useTheme } from "../theme/ThemeContext";

type UpgradeInfo = { upi_id: string; whatsapp_url: string; message: string };

export default function UpgradePage() {
  const [info, setInfo] = useState<UpgradeInfo | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const { theme } = useTheme();
  const selected = useMemo(() => {
    const q = new URLSearchParams(window.location.search);
    const planName = (q.get("plan_name") || "").trim();
    const planType = (q.get("plan_type") || "").trim();
    const priceRaw = (q.get("price_inr") || "").trim();
    const price = /^\d+$/.test(priceRaw) ? Number(priceRaw) : null;
    if (!planName && !planType && price == null) return null;
    return {
      planName: planName || "Selected plan",
      planType: planType || "",
      price,
    };
  }, []);

  useEffect(() => {
    (async () => {
      try {
        setInfo(await apiFetch<UpgradeInfo>("/subscription/upgrade-info"));
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Failed to load");
      }
    })();
  }, []);

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
  };

  const selectedPlanText = selected
    ? `${selected.planName}${selected.planType ? ` (${selected.planType})` : ""}`
    : null;
  const selectedAmountText = selected?.price != null ? `₹${selected.price}/month` : null;

  const whatsappHref = useMemo(() => {
    if (!info) return "";
    if (!selected) return info.whatsapp_url;
    try {
      const u = new URL(info.whatsapp_url);
      const msgParts = [
        `I have chosen the ${selected.planName} plan${selected.planType ? ` (${selected.planType})` : ""}.`,
        selected.price != null ? `Plan amount: ₹${selected.price}/month.` : "",
        `I will pay to UPI: ${info.upi_id}.`,
        "Please share activation confirmation after payment screenshot.",
      ].filter(Boolean);
      u.searchParams.set("text", msgParts.join(" "));
      return u.toString();
    } catch {
      return info.whatsapp_url;
    }
  }, [info, selected]);

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
          {selected && (
            <div className={`rounded-xl border p-4 sm:p-5 ${t.selectedBox}`}>
              <p className={`text-xs uppercase tracking-wide ${t.selectedTitle}`}>Selected plan</p>
              <p className={`mt-1 text-base font-semibold sm:text-lg ${t.selectedText}`}>{selectedPlanText}</p>
              {selectedAmountText && (
                <p className={`mt-1 text-sm font-medium sm:text-base ${t.selectedText}`}>
                  You have chosen the plan with rate: <strong>{selectedAmountText}</strong>.
                </p>
              )}
            </div>
          )}
          <div className={`rounded-xl border p-4 sm:p-5 ${t.upiBox}`}>
            <p className={`text-xs uppercase tracking-wide ${t.upiLabel}`}>UPI ID</p>
            <p className={`mt-1 break-all font-mono text-base sm:text-lg ${t.upiValue}`}>{info.upi_id}</p>
          </div>
          <p className={`text-sm sm:text-base ${t.msg}`}>
            {selected
              ? `You have chosen ${selectedPlanText}${selectedAmountText ? ` at ${selectedAmountText}` : ""}. Send money to this UPI ID and share payment screenshot on the WhatsApp number below.`
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
