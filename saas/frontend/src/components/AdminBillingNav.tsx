import AdminHeaderNavMenu from "./AdminHeaderNavMenu";

const BILLING_LINKS = [
  { to: "/admin/billing/payments", label: "Payments" },
  { to: "/admin/billing/invoices", label: "Invoices" },
  { to: "/admin/billing/settings", label: "Settings" },
] as const;

/** Platform Admin Billing destinations — navigation only for this step. */
export default function AdminBillingNav() {
  return <AdminHeaderNavMenu label="Billing" links={BILLING_LINKS} extraActivePrefixes={["/admin/billing"]} />;
}
