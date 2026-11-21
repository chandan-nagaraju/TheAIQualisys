import AdminBillingShell from "../components/AdminBillingShell";

const SECTION_COPY = {
  invoices: {
    title: "Invoices",
    body: "Invoice generation and GST will be added here. This page is a placeholder.",
  },
  settings: {
    title: "Billing settings",
    body: "Billing settings will be added here. This page is a placeholder.",
  },
} as const;

export type AdminBillingPlaceholderSection = keyof typeof SECTION_COPY;

export default function AdminBillingPlaceholderPage({ section }: { section: AdminBillingPlaceholderSection }) {
  const copy = SECTION_COPY[section];
  return (
    <AdminBillingShell title={copy.title}>
      <p className="text-sm text-slate-400">{copy.body}</p>
    </AdminBillingShell>
  );
}
