import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiFetch, apiUrl } from "../api";

type Product = { id: number; code: string; name: string; plans?: unknown[] };

type Installer = {
  id: number;
  product_id: number;
  version: string;
  release_channel: string;
  listing_active: boolean;
  min_windows_version: string | null;
  file_name: string | null;
  file_sha256: string | null;
  file_size_bytes: number | null;
  release_date: string | null;
  release_notes: string | null;
  has_file: boolean;
  product_code?: string;
  product_name?: string;
};

export default function AdminDesktopInstallersPage() {
  const nav = useNavigate();
  const [products, setProducts] = useState<Product[]>([]);
  const [productId, setProductId] = useState<number | null>(null);
  const [rows, setRows] = useState<Installer[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [disabled, setDisabled] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [version, setVersion] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);

  const loadProducts = async () => {
    const data = await apiFetch<Product[]>("/api/admin/desktop/products", { token: "admin" });
    setProducts(data);
    if (data.length && productId == null) setProductId(data[0].id);
  };

  const loadInstallers = async (pid: number) => {
    const data = await apiFetch<Installer[]>(`/api/admin/desktop/products/${pid}/installers`, {
      token: "admin",
    });
    setRows(data);
  };

  useEffect(() => {
    if (!localStorage.getItem("fir_admin_token")) {
      nav("/login");
      return;
    }
    (async () => {
      try {
        setDisabled(false);
        await loadProducts();
      } catch (e) {
        const m = e instanceof Error ? e.message : "Failed";
        if (/404|Not found/i.test(m)) setDisabled(true);
        else setErr(m);
      }
    })();
  }, [nav]);

  useEffect(() => {
    if (!productId) return;
    (async () => {
      try {
        await loadInstallers(productId);
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Failed to load installers");
      }
    })();
  }, [productId]);

  const createVersion = async (e: FormEvent) => {
    e.preventDefault();
    if (!productId) return;
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      await apiFetch(`/api/admin/desktop/products/${productId}/installers`, {
        method: "POST",
        token: "admin",
        body: JSON.stringify({ version, release_notes: notes || null }),
      });
      setVersion("");
      setNotes("");
      setMsg("Version registered (unpublished until file uploaded + published).");
      await loadInstallers(productId);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Create failed");
    } finally {
      setBusy(false);
    }
  };

  const upload = async (installerId: number, file: File | null) => {
    if (!file || !productId) return;
    setBusy(true);
    setErr(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const token = localStorage.getItem("fir_admin_token");
      const res = await fetch(apiUrl(`/api/admin/desktop/installers/${installerId}/upload`), {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || res.statusText);
      }
      setMsg("Installer uploaded (SHA-256 computed server-side).");
      await loadInstallers(productId);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const action = async (installerId: number, path: string, body?: object) => {
    if (!productId) return;
    setBusy(true);
    setErr(null);
    try {
      await apiFetch(`/api/admin/desktop/installers/${installerId}/${path}`, {
        method: "POST",
        token: "admin",
        body: body ? JSON.stringify(body) : "{}",
      });
      await loadInstallers(productId);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Action failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-white">Desktop installers</h1>
        <Link to="/admin" className="text-sm text-brand-500 hover:underline">
          ← Admin
        </Link>
      </div>
      <p className="text-sm text-slate-400">
        Private object storage only. No permanent public installer URLs. Soft-archive — no hard delete.
      </p>
      {disabled && (
        <p className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-4 py-3 text-sm text-amber-100">
          Desktop licensing is not enabled on this environment yet.
        </p>
      )}
      {err && <p className="text-sm text-red-400">{err}</p>}
      {msg && <p className="text-sm text-emerald-400">{msg}</p>}

      <label className="block text-sm text-slate-300">
        Product
        <select
          className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
          value={productId ?? ""}
          onChange={(e) => setProductId(parseInt(e.target.value, 10))}
        >
          {products.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} ({p.code})
            </option>
          ))}
        </select>
      </label>

      <form onSubmit={createVersion} className="space-y-3 rounded-xl border border-slate-800 bg-slate-900/50 p-4">
        <h2 className="text-sm font-semibold text-slate-200">Register version</h2>
        <input
          className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
          placeholder="Version e.g. 1.2.0"
          value={version}
          onChange={(e) => setVersion(e.target.value)}
          required
        />
        <textarea
          className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
          placeholder="Release notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
        />
        <button
          type="submit"
          disabled={busy || !version}
          className="rounded-lg bg-brand-600 px-4 py-2 text-sm text-white disabled:opacity-40"
        >
          Create unpublished version
        </button>
      </form>

      <div className="space-y-3">
        {rows.map((r) => (
          <div key={r.id} className="rounded-xl border border-slate-800 bg-slate-900/50 p-4 text-sm space-y-2">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="font-semibold text-white">
                v{r.version} · {r.release_channel} · {r.listing_active ? "published" : "unpublished"}
              </span>
              <span className="text-xs text-slate-500">{r.has_file ? "file ready" : "no file"}</span>
            </div>
            <p className="text-xs text-slate-400">
              {r.file_name || "—"} · {r.file_size_bytes != null ? `${r.file_size_bytes} bytes` : "—"} · SHA-256{" "}
              <code className="text-slate-300">{r.file_sha256 || "—"}</code>
            </p>
            {r.release_notes && <p className="text-xs text-slate-500 whitespace-pre-wrap">{r.release_notes}</p>}
            <div className="flex flex-wrap gap-2 pt-1">
              <label className="cursor-pointer rounded border border-slate-600 px-2 py-1 text-xs text-slate-200">
                Upload
                <input
                  type="file"
                  className="hidden"
                  accept=".exe,.msi,.zip,.msix"
                  onChange={(e) => void upload(r.id, e.target.files?.[0] || null)}
                />
              </label>
              <button
                type="button"
                disabled={busy}
                className="rounded border border-slate-600 px-2 py-1 text-xs"
                onClick={() => void action(r.id, "publish")}
              >
                Publish
              </button>
              <button
                type="button"
                disabled={busy}
                className="rounded border border-slate-600 px-2 py-1 text-xs"
                onClick={() => void action(r.id, "unpublish")}
              >
                Unpublish
              </button>
              {(["current", "recommended", "mandatory", "archived"] as const).map((ch) => (
                <button
                  key={ch}
                  type="button"
                  disabled={busy}
                  className="rounded border border-slate-600 px-2 py-1 text-xs capitalize"
                  onClick={() => void action(r.id, "set-channel", { channel: ch })}
                >
                  {ch}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
