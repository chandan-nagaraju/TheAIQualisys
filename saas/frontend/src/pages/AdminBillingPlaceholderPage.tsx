import { Link } from "react-router-dom";

const SECTION_COPY = {
  payments: {
    title: "Payments",
    body: "Payment verification will be added here. This page is a placeholder.",
  },
  invoices: {
    title: "Invoices",
    body: "Invoice generation and GST will be added here. This page is a placeholder.",
  },
  settings: {
    title: "Billing settings",
    body: "Billing settings will be added here. This page is a placeholder.",
  },
} as const;

export type AdminBillingSection = keyof typeof SECTION_COPY;

export default function AdminBillingPlaceholderPage({ section }: { section: AdminBillingSection }) {
  const copy = SECTION_COPY[section];
  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-white">{copy.title}</h1>
        <Link to="/admin" className="text-sm text-brand-500 hover:underline">
          ← Admin home
        </Link>
      </div>
      <p className="text-sm text-slate-400">{copy.body}</p>
    </div>
  );
}
