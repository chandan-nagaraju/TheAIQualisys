import { Link, NavLink } from "react-router-dom";

const SECTION_LINKS = [
  { to: "/admin/billing/payments", label: "Payments" },
  { to: "/admin/billing/invoices", label: "Invoices" },
  { to: "/admin/billing/settings", label: "Settings" },
] as const;

export default function AdminBillingShell({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-white">Billings</h1>
        <Link to="/admin" className="text-sm text-brand-500 hover:underline">
          ← Admin home
        </Link>
      </div>
      <div className="flex flex-wrap gap-2">
        {SECTION_LINKS.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `rounded-md px-3 py-1.5 text-sm font-medium ${
                isActive ? "bg-slate-800 text-white" : "text-slate-400 hover:bg-slate-800/80 hover:text-white"
              }`
            }
          >
            {label}
          </NavLink>
        ))}
      </div>
      <div className="space-y-2">
        <h2 className="text-lg font-semibold text-white">{title}</h2>
        {description ? <p className="text-sm text-slate-400">{description}</p> : null}
      </div>
      {children}
    </div>
  );
}
