import { Link } from "react-router-dom";

export default function WorkspaceDashboard() {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h1 className="text-2xl font-semibold text-slate-800">Dashboard</h1>
      <p className="mt-2 text-slate-600">
        Final inspection reports turn your invoice data into printable inspections: import or enter line items, complete
        inspection, then preview and download FIRs. Manage customers, parts, and company-wide FIR branding from this workspace.
      </p>
      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        <Link
          to="/workspace/upload"
          className="rounded-lg border border-slate-200 bg-slate-50 p-5 transition hover:border-blue-400 hover:bg-white"
        >
          <h2 className="font-semibold text-blue-800">Generate FIR</h2>
          <p className="mt-1 text-sm text-slate-600">Excel .xlsx / .xls → extracted table → inspection → FIR preview</p>
        </Link>
        <Link
          to="/workspace/customers"
          className="rounded-lg border border-slate-200 bg-slate-50 p-5 transition hover:border-blue-400 hover:bg-white"
        >
          <h2 className="font-semibold text-blue-800">Customers / vendors</h2>
          <p className="mt-1 text-sm text-slate-600">Vendor codes used in FIR headers</p>
        </Link>
        <Link
          to="/workspace/parts"
          className="rounded-lg border border-slate-200 bg-slate-50 p-5 transition hover:border-blue-400 hover:bg-white"
        >
          <h2 className="font-semibold text-blue-800">Parts master</h2>
          <p className="mt-1 text-sm text-slate-600">Save part data</p>
        </Link>
        <Link
          to="/workspace/settings"
          className="rounded-lg border border-slate-200 bg-slate-50 p-5 transition hover:border-blue-400 hover:bg-white"
        >
          <h2 className="font-semibold text-blue-800">Global FIR settings</h2>
          <p className="mt-1 text-sm text-slate-600">Company name, logo, signatures, format metadata</p>
        </Link>
      </div>
    </div>
  );
}
