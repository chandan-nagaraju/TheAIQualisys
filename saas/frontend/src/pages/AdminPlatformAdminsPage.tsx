import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiFetch } from "../api";

type AdminRow = {
  id: number;
  email: string;
  created_at: string | null;
};

export default function AdminPlatformAdminsPage() {
  const nav = useNavigate();
  const [me, setMe] = useState<AdminRow | null>(null);
  const [rows, setRows] = useState<AdminRow[]>([]);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [pwTarget, setPwTarget] = useState<number | null>(null);
  const [pw1, setPw1] = useState("");
  const [pw2, setPw2] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    const [mine, list] = await Promise.all([
      apiFetch<AdminRow>("/admin/me", { token: "admin" }),
      apiFetch<AdminRow[]>("/admin/platform-admins", { token: "admin" }),
    ]);
    setMe(mine);
    setRows(list);
  }

  useEffect(() => {
    const t = localStorage.getItem("fir_admin_token");
    if (!t) {
      nav("/login");
      return;
    }
    load().catch(() => {
      localStorage.removeItem("fir_admin_token");
      nav("/login");
    });
  }, [nav]);

  async function addAdmin(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    if (password !== confirm) {
      setErr("Password and confirmation do not match.");
      return;
    }
    setBusy(true);
    try {
      await apiFetch<AdminRow>("/admin/platform-admins", {
        method: "POST",
        token: "admin",
        body: JSON.stringify({ email: email.trim(), password, confirm_password: confirm }),
      });
      setEmail("");
      setPassword("");
      setConfirm("");
      setMsg("Admin added. They can sign in at /login with that email.");
      await load();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Could not add admin.");
    } finally {
      setBusy(false);
    }
  }

  async function setPasswordFor(id: number) {
    setErr(null);
    setMsg(null);
    if (pw1 !== pw2) {
      setErr("Password and confirmation do not match.");
      return;
    }
    setBusy(true);
    try {
      await apiFetch(`/admin/platform-admins/${id}`, {
        method: "PATCH",
        token: "admin",
        body: JSON.stringify({ password: pw1, confirm_password: pw2 }),
      });
      setPwTarget(null);
      setPw1("");
      setPw2("");
      setMsg("Password updated.");
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Could not set password.");
    } finally {
      setBusy(false);
    }
  }

  async function removeAdmin(row: AdminRow) {
    if (!window.confirm(`Remove platform admin ${row.email}?`)) return;
    setErr(null);
    setMsg(null);
    setBusy(true);
    try {
      await apiFetch(`/admin/platform-admins/${row.id}`, { method: "DELETE", token: "admin" });
      setMsg("Admin removed.");
      await load();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Could not delete admin.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-10">
      <div>
        <Link className="text-sm text-brand-600 hover:underline" to="/admin">
          ← All companies
        </Link>
        <h1 className="mt-2 text-2xl font-semibold text-white">Platform admins</h1>
        <p className="mt-1 max-w-2xl text-sm text-slate-400">
          Add people who can open the admin panel (companies, trials, pricing). They sign in at{" "}
          <span className="text-slate-200">/login</span> with this email — it is not a company workspace account.
          Password must be at least 8 characters.
        </p>
        <p className="mt-2 max-w-2xl text-xs text-slate-500">
          If this email is also set as <span className="font-mono">BOOTSTRAP_ADMIN_EMAIL</span> on the server, a backend
          restart can reset that account’s password to <span className="font-mono">BOOTSTRAP_ADMIN_PASSWORD</span>.
        </p>
      </div>

      {msg && <p className="text-sm text-emerald-400">{msg}</p>}
      {err && <p className="text-sm text-red-400">{err}</p>}

      <form
        onSubmit={addAdmin}
        className="max-w-xl space-y-3 rounded-2xl border border-slate-800 bg-slate-900/40 p-6"
      >
        <h2 className="text-lg font-semibold text-white">Add admin</h2>
        <div>
          <label className="block text-xs text-slate-500">Email</label>
          <input
            type="email"
            required
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="admin@theaiqualisys.com"
          />
        </div>
        <div>
          <label className="block text-xs text-slate-500">Password</label>
          <input
            type="password"
            required
            minLength={8}
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-xs text-slate-500">Confirm password</label>
          <input
            type="password"
            required
            minLength={8}
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
        </div>
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
        >
          {busy ? "Saving…" : "Add admin"}
        </button>
      </form>

      <section>
        <h2 className="text-lg font-semibold text-white">Existing admins ({rows.length})</h2>
        <div className="mt-4 overflow-x-auto rounded-xl border border-slate-800">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-900/80 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Created</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800 text-slate-200">
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="px-4 py-3">
                    {r.email}
                    {me?.id === r.id ? (
                      <span className="ml-2 text-xs text-amber-400">(you)</span>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 text-slate-400">
                    {r.created_at ? r.created_at.slice(0, 10) : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        className="rounded-lg border border-slate-600 px-3 py-1 text-xs hover:bg-slate-800"
                        onClick={() => {
                          setPwTarget(r.id);
                          setPw1("");
                          setPw2("");
                          setErr(null);
                        }}
                      >
                        Set password
                      </button>
                      {me?.id !== r.id ? (
                        <button
                          type="button"
                          disabled={busy}
                          className="rounded-lg border border-red-900/60 px-3 py-1 text-xs text-red-300 hover:bg-red-950/40 disabled:opacity-50"
                          onClick={() => void removeAdmin(r)}
                        >
                          Remove
                        </button>
                      ) : null}
                    </div>
                    {pwTarget === r.id ? (
                      <div className="mt-3 max-w-sm space-y-2">
                        <input
                          type="password"
                          minLength={8}
                          placeholder="New password"
                          className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
                          value={pw1}
                          onChange={(e) => setPw1(e.target.value)}
                        />
                        <input
                          type="password"
                          minLength={8}
                          placeholder="Confirm password"
                          className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
                          value={pw2}
                          onChange={(e) => setPw2(e.target.value)}
                        />
                        <div className="flex gap-2">
                          <button
                            type="button"
                            disabled={busy}
                            className="rounded-lg bg-emerald-600 px-3 py-1 text-xs font-semibold text-white disabled:opacity-50"
                            onClick={() => void setPasswordFor(r.id)}
                          >
                            Save password
                          </button>
                          <button
                            type="button"
                            className="rounded-lg border border-slate-600 px-3 py-1 text-xs"
                            onClick={() => setPwTarget(null)}
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : null}
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
