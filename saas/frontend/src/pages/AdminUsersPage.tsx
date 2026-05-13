import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiFetch } from "../api";

type TenantUser = {
  user_id: number;
  email: string;
  name: string | null;
  is_blocked: boolean;
  created_at: string;
  company_id: number;
  company_name: string;
  company_vendor_code: string;
  plan_type: string;
  subscription_status: string;
};

type FirCustomer = {
  customer_id: number;
  vendor_code: string;
  name: string;
  company_id: number;
  company_name: string;
  company_vendor_code: string;
};

function norm(s: string) {
  return s.toLowerCase().trim();
}

export default function AdminUsersPage() {
  const nav = useNavigate();
  const [tenantUsers, setTenantUsers] = useState<TenantUser[]>([]);
  const [firCustomers, setFirCustomers] = useState<FirCustomer[]>([]);
  const [q, setQ] = useState("");
  const [busyUserId, setBusyUserId] = useState<number | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    const t = localStorage.getItem("fir_admin_token");
    if (!t) {
      nav("/login");
      return;
    }
    const [u, c] = await Promise.all([
      apiFetch<TenantUser[]>("/admin/tenant-users", { token: "admin" }),
      apiFetch<FirCustomer[]>("/admin/fir-customers", { token: "admin" }),
    ]);
    setTenantUsers(u);
    setFirCustomers(c);
  }, [nav]);

  useEffect(() => {
    loadAll().catch(() => {
      localStorage.removeItem("fir_admin_token");
      nav("/login");
    });
  }, [loadAll, nav]);

  async function toggleUserBlocked(userId: number, currentlyBlocked: boolean) {
    setBusyUserId(userId);
    setErr(null);
    setMsg(null);
    try {
      const endpoint = currentlyBlocked
        ? `/admin/tenant-users/${userId}/unblock`
        : `/admin/tenant-users/${userId}/block`;
      const res = await apiFetch<{ ok: boolean; user_id: number; is_blocked: boolean }>(endpoint, {
        token: "admin",
        method: "POST",
        body: "{}",
      });
      setTenantUsers((prev) =>
        prev.map((u) => (u.user_id === userId ? { ...u, is_blocked: res.is_blocked } : u)),
      );
      setMsg(res.is_blocked ? "User blocked successfully." : "User unblocked successfully.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to update user.");
    } finally {
      setBusyUserId(null);
    }
  }

  async function deleteUser(userId: number, email: string) {
    if (!window.confirm(`Delete user ${email}? This cannot be undone.`)) return;
    setBusyUserId(userId);
    setErr(null);
    setMsg(null);
    try {
      await apiFetch(`/admin/tenant-users/${userId}`, {
        token: "admin",
        method: "DELETE",
      });
      await loadAll();
      setMsg("User deleted successfully.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to delete user.");
    } finally {
      setBusyUserId(null);
    }
  }

  const needle = norm(q);
  const filteredUsers = useMemo(() => {
    if (!needle) return tenantUsers;
    return tenantUsers.filter(
      (r) =>
        norm(r.email).includes(needle) ||
        norm(r.company_name).includes(needle) ||
        norm(r.company_vendor_code).includes(needle) ||
        (r.name && norm(r.name).includes(needle)),
    );
  }, [tenantUsers, needle]);

  const filteredCustomers = useMemo(() => {
    if (!needle) return firCustomers;
    return firCustomers.filter(
      (r) =>
        norm(r.name).includes(needle) ||
        norm(r.vendor_code).includes(needle) ||
        norm(r.company_name).includes(needle) ||
        norm(r.company_vendor_code).includes(needle),
    );
  }, [firCustomers, needle]);

  return (
    <div className="space-y-10">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <Link className="text-sm text-brand-600 hover:underline" to="/admin">
            ← All companies
          </Link>
          <h1 className="mt-2 text-2xl font-semibold text-white">Users &amp; customers (all tenants)</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-400">
            <strong className="text-slate-300">Tenant users</strong> are login accounts for each company.{" "}
            <strong className="text-slate-300">Deleting a user</strong> only removes that sign-in; the company, FIR
            customers, and parts stay in the database and still appear on the main admin companies list. To remove an
            entire customer, open <strong className="text-slate-300">Manage</strong> on that company and use{" "}
            <strong className="text-slate-300">Delete tenant</strong>.{" "}
            <strong className="text-slate-300">FIR customers</strong> are vendor records used at upload / inspection
            (customer-facing process).
          </p>
        </div>
      </div>

      <div>
        <label className="block text-xs uppercase tracking-wide text-slate-500">Filter both tables</label>
        <input
          type="search"
          placeholder="Email, company name, vendor code, customer name…"
          className="mt-1 w-full max-w-xl rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white placeholder:text-slate-600"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        {msg && <p className="mt-2 text-sm text-emerald-400">{msg}</p>}
        {err && <p className="mt-2 text-sm text-red-400">{err}</p>}
      </div>

      <section id="tenant-users">
        <h2 className="text-lg font-semibold text-white">Tenant users ({filteredUsers.length})</h2>
        <p className="mt-1 text-xs text-slate-500">Sign-in accounts per company — use to verify who can access the workspace.</p>
        <div className="mt-4 overflow-x-auto rounded-xl border border-slate-800">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-900/80 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Company</th>
                <th className="px-4 py-3">Vendor</th>
                <th className="px-4 py-3">Plan</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">User state</th>
                <th className="px-4 py-3">Joined</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {filteredUsers.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-4 py-6 text-center text-slate-500">
                    No rows match.
                  </td>
                </tr>
              )}
              {filteredUsers.map((r) => (
                <tr key={r.user_id} className="hover:bg-slate-900/40">
                  <td className="px-4 py-3 font-mono text-slate-200">{r.email}</td>
                  <td className="px-4 py-3 text-slate-300">{r.name || "—"}</td>
                  <td className="px-4 py-3 text-slate-200">{r.company_name}</td>
                  <td className="px-4 py-3 font-mono text-slate-400">{r.company_vendor_code}</td>
                  <td className="px-4 py-3 text-slate-400">{r.plan_type}</td>
                  <td className="px-4 py-3 text-slate-400">{r.subscription_status}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${
                        r.is_blocked ? "bg-red-500/15 text-red-300" : "bg-emerald-500/15 text-emerald-300"
                      }`}
                    >
                      {r.is_blocked ? "blocked" : "active"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-500">{new Date(r.created_at).toLocaleString()}</td>
                  <td className="px-4 py-3 text-right">
                    <div className="inline-flex flex-wrap items-center justify-end gap-3">
                      <button
                        type="button"
                        className="text-amber-300 hover:underline disabled:opacity-50"
                        disabled={busyUserId === r.user_id}
                        onClick={() => void toggleUserBlocked(r.user_id, r.is_blocked)}
                      >
                        {r.is_blocked ? "Unblock" : "Block"}
                      </button>
                      <button
                        type="button"
                        className="text-red-400 hover:underline disabled:opacity-50"
                        disabled={busyUserId === r.user_id}
                        onClick={() => void deleteUser(r.user_id, r.email)}
                      >
                        Delete
                      </button>
                      <Link className="text-brand-600 hover:underline" to={`/admin/companies/${r.company_id}`}>
                        Company
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section id="fir-customers">
        <h2 className="text-lg font-semibold text-white">FIR customers ({filteredCustomers.length})</h2>
        <p className="mt-1 text-xs text-slate-500">
          End-customer / vendor codes configured in each tenant (upload flow). Helps trace issues when something fails at
          customer selection or invoice context.
        </p>
        <div className="mt-4 overflow-x-auto rounded-xl border border-slate-800">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-900/80 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">Customer name</th>
                <th className="px-4 py-3">Cust. vendor code</th>
                <th className="px-4 py-3">Company</th>
                <th className="px-4 py-3">Co. vendor</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {filteredCustomers.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-slate-500">
                    No rows match.
                  </td>
                </tr>
              )}
              {filteredCustomers.map((r) => (
                <tr key={`${r.company_id}-${r.customer_id}`} className="hover:bg-slate-900/40">
                  <td className="px-4 py-3 text-slate-200">{r.name}</td>
                  <td className="px-4 py-3 font-mono text-slate-400">{r.vendor_code}</td>
                  <td className="px-4 py-3 text-slate-200">{r.company_name}</td>
                  <td className="px-4 py-3 font-mono text-slate-400">{r.company_vendor_code}</td>
                  <td className="px-4 py-3 text-right">
                    <Link className="text-brand-600 hover:underline" to={`/admin/companies/${r.company_id}`}>
                      Company
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
