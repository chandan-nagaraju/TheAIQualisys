import { useTheme } from "../theme/ThemeContext";

type Kind = "active" | "trial" | "locked" | "neutral";

function kindFromStatus(status: string): Kind {
  const s = status.toLowerCase();
  if (s.includes("active")) return "active";
  if (s.includes("trial")) return "trial";
  if (s.includes("not subscribed") || s.includes("expired") || s.includes("denied") || s.includes("locked"))
    return "locked";
  return "neutral";
}

/** Theme-safe subscription labels (billing, etc.) — contrast checked for dark / light / grey. */
export default function SubscriptionStatusPill({ status }: { status: string }) {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const k = kindFromStatus(status);

  const cls = isDark
    ? {
        active: "bg-emerald-500/20 text-emerald-300 ring-1 ring-inset ring-emerald-500/35",
        trial: "bg-sky-500/20 text-sky-300 ring-1 ring-inset ring-sky-500/35",
        locked: "bg-slate-700 text-slate-200 ring-1 ring-inset ring-slate-500/40",
        neutral: "bg-slate-700 text-slate-200 ring-1 ring-inset ring-slate-500/40",
      }[k]
    : {
        active: "bg-emerald-100 text-emerald-900 ring-1 ring-inset ring-emerald-200",
        trial: "bg-sky-100 text-sky-900 ring-1 ring-inset ring-sky-200",
        locked: "bg-slate-200 text-slate-800 ring-1 ring-inset ring-slate-300",
        neutral: "bg-slate-200 text-slate-800 ring-1 ring-inset ring-slate-300",
      }[k];

  return (
    <span className={`inline-flex shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold ${cls}`}>{status}</span>
  );
}
