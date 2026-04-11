import { type ReactNode, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { apiFetch } from "../api";
import { QMS_MODULES, type QmsModuleSlug } from "../moduleCatalog";
import { useTheme } from "../theme/ThemeContext";

type Me = {
  fir_reports_this_month: number;
  usage_this_month: number;
  can_access_fir_workspace: boolean;
};

type OverviewModule = {
  slug: string;
  module_name: string;
  access: string;
  badge: string;
  actions_remaining: number | null;
  days_remaining: number | null;
  trial_expired_message: string | null;
  notify_trial_ending: boolean;
};

type Overview = { modules: OverviewModule[] };

type PricingRow = {
  module_name: string;
  trial_days: number;
  usage_limit: number;
};

const badgeStylesDark: Record<string, string> = {
  live: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  trial: "bg-sky-500/15 text-sky-300 ring-sky-500/30",
  locked: "bg-slate-600/30 text-slate-400 ring-slate-500/30",
  coming_soon: "bg-amber-500/15 text-amber-200 ring-amber-500/30",
};

/** Light + grey: solid pastel chips so text/background pairs stay WCAG-friendly */
const badgeStylesLight: Record<string, string> = {
  live: "bg-emerald-100 text-emerald-900 ring-emerald-300/70",
  trial: "bg-sky-100 text-sky-900 ring-sky-300/70",
  locked: "bg-slate-200 text-slate-800 ring-slate-400/80",
  coming_soon: "bg-amber-100 text-amber-950 ring-amber-300/80",
};

export default function ModulesDashboardPage() {
  const nav = useNavigate();
  const loc = useLocation();
  const workspaceBlocked = Boolean((loc.state as { workspaceBlocked?: boolean } | null)?.workspaceBlocked);
  const token = useMemo(() => localStorage.getItem("fir_token"), []);
  const [me, setMe] = useState<Me | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [pricingRows, setPricingRows] = useState<PricingRow[] | null>(null);

  useEffect(() => {
    if (!token) {
      nav("/login");
      return;
    }
    (async () => {
      try {
        const [m, o, pr] = await Promise.all([
          apiFetch<Me>("/api/v2/me"),
          apiFetch<Overview>("/api/modules/overview"),
          apiFetch<PricingRow[]>("/api/pricing/modules"),
        ]);
        setMe(m);
        setOverview(o);
        setPricingRows(pr);
      } catch {
        nav("/login");
      }
    })();
  }, [nav, token]);

  const overviewBySlug = useMemo(() => {
    const map = new Map<string, OverviewModule>();
    overview?.modules.forEach((row) => map.set(row.slug, row));
    return map;
  }, [overview]);

  const trialAlerts =
    overview?.modules.filter((m) => m.notify_trial_ending && m.access === "trial") ?? [];

  const priceByModule = useMemo(() => {
    const map = new Map<string, PricingRow>();
    pricingRows?.forEach((r) => map.set(r.module_name, r));
    return map;
  }, [pricingRows]);

  if (!me || !overview || !pricingRows) {
    return <p className="text-slate-400">Loading…</p>;
  }

  return (
    <div className="space-y-10">
      <div>
        <h1 className="text-2xl font-semibold text-white">QMS dashboard</h1>
        <p className="mt-1 text-sm text-slate-400">
          Choose a module. FIR is fully enabled; other modules use trial then subscription.
        </p>
      </div>

      {workspaceBlocked && (
        <div className="rounded-lg border border-amber-700/50 bg-amber-950/30 px-4 py-3 text-sm text-amber-100">
          The FIR workspace is unavailable until you have an active trial or paid FIR plan. Open{" "}
          <Link className="font-semibold text-brand-500 hover:underline" to="/upgrade">
            Upgrade
          </Link>{" "}
          or check{" "}
          <Link className="font-semibold text-brand-500 hover:underline" to="/dashboard/billing">
            usage &amp; billing
          </Link>
          .
        </div>
      )}

      {trialAlerts.length > 0 && (
        <div className="rounded-lg border border-sky-700/40 bg-sky-950/30 px-4 py-3 text-sm text-sky-100">
          Trial ending soon:{" "}
          {trialAlerts.map((m) => (
            <span key={m.slug} className="font-medium">
              {QMS_MODULES.find((x) => x.slug === (m.slug as QmsModuleSlug))?.title ?? m.slug}
              {m.days_remaining != null ? ` (${m.days_remaining}d left)` : ""}
              {m.actions_remaining != null ? ` · ${m.actions_remaining} actions left` : ""}
            </span>
          ))}
        </div>
      )}

      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
        <ModuleCard
          title="FIR Automation"
          description="Invoices, inspection, parts master, printable FIR — full workspace."
          badgeLabel="Live"
          badgeKey="live"
          footer={
            me.can_access_fir_workspace ? (
              <Link
                to="/workspace/dashboard"
                className="mt-4 inline-flex w-full justify-center rounded-lg bg-brand-600 py-2.5 text-sm font-semibold text-white hover:bg-brand-500"
              >
                Open FIR workspace
              </Link>
            ) : (
              <Link
                to="/upgrade"
                className="mt-4 inline-flex w-full justify-center rounded-lg border border-amber-600/50 py-2.5 text-sm font-semibold text-amber-200 hover:bg-amber-950/40"
              >
                Activate FIR access
              </Link>
            )
          }
          stats={
            <p className="mt-2 text-xs text-slate-500">
              FIR reports this month: <span className="text-slate-300">{me.fir_reports_this_month}</span> · Combined
              usage: <span className="text-slate-300">{me.usage_this_month}</span>
            </p>
          }
        />

        {QMS_MODULES.map((def) => {
          const row = overviewBySlug.get(def.slug);
          const badgeKey =
            row?.badge === "live" ? "live" : row?.badge === "trial" ? "trial" : row?.access === "denied" ? "locked" : "locked";
          const pricingHref = `/pricing/modules/${def.slug}`;
          return (
            <ModuleCard
              key={def.slug}
              title={def.title}
              description={def.shortDescription}
              badgeLabel={row?.badge === "trial" ? "Trial" : row?.badge === "live" ? "Live" : "Locked"}
              badgeKey={badgeKey}
              stats={
                row?.access === "trial" ? (
                  <p className="mt-2 text-xs text-slate-500">
                    {row.days_remaining != null ? `${row.days_remaining} days left · ` : ""}
                    {row.actions_remaining != null ? `${row.actions_remaining} trial actions left` : ""}
                  </p>
                ) : row?.access === "denied" && row.trial_expired_message ? (
                  <p className="mt-2 text-xs text-amber-300/90">{row.trial_expired_message}</p>
                ) : def.landingStatus === "available" ? (
                  <p className="mt-2 text-xs text-slate-500">
                    {(() => {
                      const pr = priceByModule.get(def.moduleName);
                      const d = pr?.trial_days ?? 14;
                      const u = pr?.usage_limit ?? 5;
                      return `${d}-day trial · ${u} actions when you open the module.`;
                    })()}
                  </p>
                ) : (
                  <p className="mt-2 text-xs text-slate-500">Not available yet.</p>
                )
              }
              footer={
                <div className="mt-4 flex flex-col gap-2">
                  <Link
                    to={`/modules/${def.slug}`}
                    className="inline-flex w-full justify-center rounded-lg bg-slate-100 py-2.5 text-sm font-semibold text-slate-900 hover:bg-white"
                  >
                    Open module
                  </Link>
                  <Link
                    to={pricingHref}
                    className="text-center text-xs font-medium text-brand-500 hover:underline"
                  >
                    View pricing &amp; enroll
                  </Link>
                </div>
              }
            />
          );
        })}
      </div>
    </div>
  );
}

function ModuleCard({
  title,
  description,
  badgeLabel,
  badgeKey,
  stats,
  footer,
}: {
  title: string;
  description: string;
  badgeLabel: string;
  badgeKey: string;
  stats?: ReactNode;
  footer: ReactNode;
}) {
  const { theme } = useTheme();
  const badgeMap = theme === "dark" ? badgeStylesDark : badgeStylesLight;
  const cls = badgeMap[badgeKey] ?? badgeMap.locked;

  /** Dark: layered border + top highlight + depth — light/grey keep flat cards (CSS overrides handle surfaces). */
  const cardClass =
    theme === "dark"
      ? "flex flex-col rounded-2xl border border-slate-500/55 bg-gradient-to-b from-slate-800/50 to-slate-950/80 p-5 shadow-[0_12px_40px_-16px_rgba(0,0,0,0.75),inset_0_1px_0_0_rgba(255,255,255,0.08),0_0_0_1px_rgba(56,189,248,0.12)]"
      : "flex flex-col rounded-2xl border border-slate-800 bg-slate-900/50 p-5 shadow-lg shadow-black/20";

  return (
    <div className={cardClass}>
      <div className="flex items-start justify-between gap-2">
        <h2 className="text-lg font-semibold text-white">{title}</h2>
        <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${cls}`}>
          {badgeLabel}
        </span>
      </div>
      <p className="mt-2 flex-1 text-sm text-slate-400">{description}</p>
      {stats}
      {footer}
    </div>
  );
}
