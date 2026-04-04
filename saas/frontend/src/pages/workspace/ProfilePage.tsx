import { Link } from "react-router-dom";

export default function ProfilePage() {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
      <h1 className="text-xl font-semibold text-slate-900">Profile settings</h1>
      <p className="mt-2 text-sm text-slate-600">
        Manage your account-level options from here.
      </p>

      <div className="mt-6 grid gap-3 sm:max-w-md">
        <Link
          to="/profile/change-password"
          className="inline-flex min-h-11 items-center justify-center rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50"
        >
          Change password
        </Link>
      </div>
    </div>
  );
}
