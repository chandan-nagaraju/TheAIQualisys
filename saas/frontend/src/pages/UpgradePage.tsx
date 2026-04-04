import { useEffect, useState } from "react";
import { apiFetch } from "../api";
import { useTheme } from "../theme/ThemeContext";

type UpgradeInfo = { upi_id: string; whatsapp_url: string; message: string };

export default function UpgradePage() {
  const [info, setInfo] = useState<UpgradeInfo | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const { theme } = useTheme();

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
  };

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
          <div className={`rounded-xl border p-4 sm:p-5 ${t.upiBox}`}>
            <p className={`text-xs uppercase tracking-wide ${t.upiLabel}`}>UPI ID</p>
            <p className={`mt-1 break-all font-mono text-base sm:text-lg ${t.upiValue}`}>{info.upi_id}</p>
          </div>
          <p className={`text-sm sm:text-base ${t.msg}`}>{info.message}</p>
          <a
            href={info.whatsapp_url}
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
