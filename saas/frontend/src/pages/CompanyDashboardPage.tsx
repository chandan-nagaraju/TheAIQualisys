import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { apiFetch } from "../api";
import SubscriptionStatusPill from "../components/SubscriptionStatusPill";

type BillingOverview = {
  company_name: string;
  vendor_code: string;
  plan_name: string;
  enable_subscription: boolean;
  company_status: string;
  trial_end_date: string | null;
  subscription_start: string | null;
  subscription_end: string | null;
  modules: {
    module_key: string;
    display_name: string;
    subscription_status: string;
    reports_this_month: number | null;
    combined_usage_this_month: number | null;
    usage_limit: number | null;
    remaining: number | null;
    trial_actions_used: number | null;
    trial_actions_limit: number | null;
    trial_actions_remaining: number | null;
  }[];
  can_access_fir_workspace: boolean;
  subscription_message: string | null;
};

export default function CompanyDashboardPage() {
  const nav = useNavigate();
  const loc = useLocation();
  const workspaceBlocked = Boolean((loc.state as { workspaceBlocked?: boolean } | null)?.workspaceBlocked);
  const token = useMemo(() => localStorage.getItem("fir_token"), []);
  const [data, setData] = useState<BillingOverview | null>(null);

  useEffect(() => {
    if (!token) {
      nav("/login");
      return;
    }
    (async () => {
      try {
        setData(await apiFetch<BillingOverview>("/api/billing/overview"));
      } catch {
        nav("/login");
      }
    })();
  }, [nav, token]);

  if (!data) {
    return <p className="text-slate-400">Loading…</p>;
  }

  const section = "rounded-2xl border border-slate-800 bg-slate-900/50 p-6 shadow-lg shadow-black/10";

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-white">Usage &amp; billing</h1>
        <p className="mt-1 text-sm text-slate-400">Subscription status, modules, and usage in one place.</p>
      </div>

      {workspaceBlocked && (
        <div className="rounded-lg border border-amber-700/50 bg-amber-950/30 px-4 py-3 text-sm text-amber-100">
          The FIR workspace is unavailable until you have an active trial or paid FIR plan.{" "}
          <Link className="font-semibold text-brand-500 hover:underline" to="/upgrade">
            Upgrade
          </Link>{" "}
          or review{" "}
          <Link className="font-semibold text-brand-500 hover:underline" to="/dashboard/billing">
            this page
          </Link>
          .
        </div>
      )}

      {!data.enable_subscription && (
        <div className="rounded-lg border border-sky-700/40 bg-sky-950/25 px-4 py-3 text-sm text-sky-100">
          Subscription enforcement is off in this environment (FIR workspace and limits are not blocked). In production,
          set <code className="rounded bg-slate-800 px-1">ENABLE_SUBSCRIPTION=true</code>.
        </div>
      )}

      {/* Section 1 */}
      <section className={section}>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Company info</h2>
        <dl className="mt-4 grid gap-3 sm:grid-cols-3">
          <div>
            <dt className="text-xs text-slate-500">Company name</dt>
            <dd className="mt-1 font-medium text-white">{data.company_name}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Plan</dt>
            <dd className="mt-1 font-medium text-white">{data.plan_name}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Status</dt>
            <dd className="mt-1 font-medium text-white">{data.company_status}</dd>
          </div>
        </dl>
        <p className="mt-3 text-xs text-slate-500">Vendor code: {data.vendor_code}</p>
      </section>

      {/* Section 2 */}
      <section className={section}>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Subscribed modules</h2>
        <ul className="mt-4 divide-y divide-slate-800 rounded-xl border border-slate-800">
          {data.modules.map((m) => (
            <li key={m.module_key} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
              <span className="font-medium text-slate-200">{m.display_name}</span>
              <SubscriptionStatusPill status={m.subscription_status} />
            </li>
          ))}
        </ul>
      </section>

      {/* Section 3 */}
      <section className={section}>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Usage details</h2>
        <div className="mt-4 space-y-6">
          {data.modules.map((m) => (
            <div key={`u-${m.module_key}`} className="border-b border-slate-800 pb-4 last:border-0 last:pb-0">
              <h3 className="text-sm font-semibold text-white">{m.display_name}</h3>
              {m.module_key === "fir" ? (
                <dl className="mt-2 grid gap-2 text-sm sm:grid-cols-3">
                  <div>
                    <dt className="text-slate-500">FIR reports (this month)</dt>
                    <dd className="text-slate-200">{m.reports_this_month ?? 0}</dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Combined usage cap</dt>
                    <dd className="text-slate-200">
                      {m.usage_limit == null ? "Unlimited" : m.usage_limit}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Remaining (invoices + reports)</dt>
                    <dd className="text-slate-200">
                      {m.usage_limit == null ? "—" : m.remaining ?? 0}
                    </dd>
                  </div>
                </dl>
              ) : (
                <dl className="mt-2 grid gap-2 text-sm sm:grid-cols-3">
                  <div>
                    <dt className="text-slate-500">Trial actions used</dt>
                    <dd className="text-slate-200">{m.trial_actions_used ?? 0}</dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Trial action limit</dt>
                    <dd className="text-slate-200">{m.trial_actions_limit ?? "—"}</dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Remaining</dt>
                    <dd className="text-slate-200">
                      {m.subscription_status === "Active"
                        ? "Full access"
                        : m.trial_actions_remaining ?? "—"}
                    </dd>
                  </div>
                </dl>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Section 4 */}
      <section className={section}>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Subscription period</h2>
        <dl className="mt-4 grid gap-3 sm:grid-cols-3">
          <div>
            <dt className="text-xs text-slate-500">Subscription start</dt>
            <dd className="mt-1 text-slate-200">{data.subscription_start ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Subscription end</dt>
            <dd className="mt-1 text-slate-200">{data.subscription_end ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Trial expiry</dt>
            <dd className="mt-1 text-slate-200">{data.trial_end_date ?? "—"}</dd>
          </div>
        </dl>
      </section>

      {data.subscription_message && (
        <p className="text-sm text-amber-300">{data.subscription_message}</p>
      )}

      {/* Section 5 */}
      <section className={`${section} flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between`}>
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Next steps</h2>
          <p className="mt-1 text-sm text-slate-400">
            Upgrade your FIR plan or enroll in additional QMS modules when you are ready.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link
            to="/upgrade"
            className="inline-flex justify-center rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-brand-500"
          >
            Upgrade plan
          </Link>
          <Link
            to="/dashboard"
            className="inline-flex justify-center rounded-lg border border-slate-600 px-5 py-2.5 text-sm font-semibold text-slate-200 hover:border-slate-500"
          >
            Enroll in modules
          </Link>
        </div>
      </section>

      <p className="text-center text-sm text-slate-500">
        Open the full FIR workspace from the{" "}
        <Link className="text-brand-500 hover:underline" to="/dashboard">
          module dashboard
        </Link>
        {data.can_access_fir_workspace ? (
          <>
            {" "}
            or{" "}
            <Link className="text-brand-500 hover:underline" to="/workspace/dashboard">
              go directly to FIR
            </Link>
          </>
        ) : null}
        .
      </p>
    </div>
  );
}
