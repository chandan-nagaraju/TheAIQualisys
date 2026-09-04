import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiFetch } from "../api";

type DesktopPlan = {
  id: number;
  product_id: number;
  code: string;
  name: string;
  description: string | null;
  price_inr: number;
  duration_days: number;
  seats: number;
  listing_active: boolean;
  sort_order: number;
};

type DesktopProduct = {
  id: number;
  code: string;
  name: string;
  description: string | null;
  listing_active: boolean;
  trial_enabled: boolean;
  trial_duration_days: number;
  sort_order: number;
  buy_url_path: string | null;
  plans: DesktopPlan[];
};

function PlanEditor({
  plan,
  onSaved,
}: {
  plan: DesktopPlan;
  onSaved: () => void;
}) {
  const [name, setName] = useState(plan.name);
  const [code, setCode] = useState(plan.code);
  const [price, setPrice] = useState(String(plan.price_inr));
  const [duration, setDuration] = useState(String(plan.duration_days));
  const [listingActive, setListingActive] = useState(plan.listing_active);
  const [status, setStatus] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setName(plan.name);
    setCode(plan.code);
    setPrice(String(plan.price_inr));
    setDuration(String(plan.duration_days));
    setListingActive(plan.listing_active);
    setStatus(null);
    setErr(null);
  }, [plan]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setStatus(null);
    try {
      await apiFetch(`/api/admin/desktop/plans/${plan.id}`, {
        method: "PATCH",
        token: "admin",
        body: JSON.stringify({
          name,
          code,
          price_inr: parseInt(price, 10),
          duration_days: parseInt(duration, 10),
          listing_active: listingActive,
        }),
      });
      setStatus("Saved.");
      onSaved();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Save failed");
    }
  }

  return (
    <form onSubmit={onSubmit} className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 space-y-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm font-medium text-white">{plan.name}</p>
        <span className="text-xs text-slate-500">
          seats=1 (fixed) · id {plan.id}
        </span>
      </div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <label className="block text-xs text-slate-500">
          Name
          <input
            className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label className="block text-xs text-slate-500">
          Code
          <input
            className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
        </label>
        <label className="block text-xs text-slate-500">
          Price (₹ / seat / term)
          <input
            type="number"
            min={0}
            className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
          />
        </label>
        <label className="block text-xs text-slate-500">
          Duration (days)
          <input
            type="number"
            min={1}
            className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
            value={duration}
            onChange={(e) => setDuration(e.target.value)}
          />
        </label>
      </div>
      <label className="block text-xs text-slate-500">
        Listing
        <select
          className="mt-1 w-full max-w-xs rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
          value={listingActive ? "active" : "inactive"}
          onChange={(e) => setListingActive(e.target.value === "active")}
        >
          <option value="active">Active — visible in customer catalog when product is active</option>
          <option value="inactive">Inactive — hidden from customer catalog</option>
        </select>
      </label>
      {err && <p className="text-xs text-red-400">{err}</p>}
      {status && <p className="text-xs text-emerald-400">{status}</p>}
      <button
        type="submit"
        className="rounded bg-brand-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-500"
      >
        Save plan
      </button>
    </form>
  );
}

function ProductCard({
  product,
  onSaved,
}: {
  product: DesktopProduct;
  onSaved: () => void;
}) {
  const [name, setName] = useState(product.name);
  const [description, setDescription] = useState(product.description ?? "");
  const [listingActive, setListingActive] = useState(product.listing_active);
  const [sortOrder, setSortOrder] = useState(String(product.sort_order));
  const [status, setStatus] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [newCode, setNewCode] = useState("");
  const [newName, setNewName] = useState("");
  const [newPrice, setNewPrice] = useState("4999");
  const [newDuration, setNewDuration] = useState("365");
  const [createErr, setCreateErr] = useState<string | null>(null);

  useEffect(() => {
    setName(product.name);
    setDescription(product.description ?? "");
    setListingActive(product.listing_active);
    setSortOrder(String(product.sort_order));
    setStatus(null);
    setErr(null);
  }, [product]);

  async function saveProduct(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setStatus(null);
    try {
      await apiFetch(`/api/admin/desktop/products/${product.id}`, {
        method: "PATCH",
        token: "admin",
        body: JSON.stringify({
          name,
          description: description.trim() === "" ? null : description,
          listing_active: listingActive,
          sort_order: parseInt(sortOrder, 10),
        }),
      });
      setStatus("Product saved.");
      onSaved();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Save failed");
    }
  }

  async function createPlan(e: FormEvent) {
    e.preventDefault();
    setCreateErr(null);
    try {
      await apiFetch(`/api/admin/desktop/products/${product.id}/plans`, {
        method: "POST",
        token: "admin",
        body: JSON.stringify({
          code: newCode,
          name: newName,
          price_inr: parseInt(newPrice, 10),
          duration_days: parseInt(newDuration, 10),
          listing_active: true,
        }),
      });
      setNewCode("");
      setNewName("");
      onSaved();
    } catch (ex) {
      setCreateErr(ex instanceof Error ? ex.message : "Create failed");
    }
  }

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/50 p-4 space-y-4">
      <form onSubmit={saveProduct} className="space-y-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-lg font-semibold text-white">{product.name}</h2>
          <code className="text-xs text-slate-500">{product.code}</code>
        </div>
        <p className="text-xs text-slate-500">
          One paid key = one website user + one PC + this product. Checkout seat count mints independent keys (Phase 4).
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-xs text-slate-500">
            Display name
            <input
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="block text-xs text-slate-500">
            Sort order
            <input
              type="number"
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value)}
            />
          </label>
        </div>
        <label className="block text-xs text-slate-500">
          Description
          <textarea
            className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
            rows={2}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
        <label className="block text-xs text-slate-500">
          Product listing
          <select
            className="mt-1 w-full max-w-md rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
            value={listingActive ? "active" : "inactive"}
            onChange={(e) => setListingActive(e.target.value === "active")}
          >
            <option value="active">Active — shown in Software catalog when flag is on</option>
            <option value="inactive">Inactive — hidden from customers</option>
          </select>
        </label>
        {err && <p className="text-xs text-red-400">{err}</p>}
        {status && <p className="text-xs text-emerald-400">{status}</p>}
        <button
          type="submit"
          className="rounded bg-brand-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-500"
        >
          Save product
        </button>
      </form>

      <div className="space-y-2">
        <h3 className="text-sm font-semibold text-slate-200">Plans (1 seat each)</h3>
        {product.plans.map((pl) => (
          <PlanEditor key={pl.id} plan={pl} onSaved={onSaved} />
        ))}
        {product.plans.length === 0 && (
          <p className="text-xs text-slate-500">No plans yet — add one below.</p>
        )}
      </div>

      <form onSubmit={createPlan} className="rounded-lg border border-dashed border-slate-700 p-3 space-y-2">
        <p className="text-xs font-medium text-slate-300">Add plan</p>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <input
            placeholder="Code e.g. ANNUAL_1SEAT"
            className="rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
            value={newCode}
            onChange={(e) => setNewCode(e.target.value)}
            required
          />
          <input
            placeholder="Name"
            className="rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            required
          />
          <input
            type="number"
            min={0}
            placeholder="Price ₹"
            className="rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
            value={newPrice}
            onChange={(e) => setNewPrice(e.target.value)}
            required
          />
          <input
            type="number"
            min={1}
            placeholder="Days"
            className="rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
            value={newDuration}
            onChange={(e) => setNewDuration(e.target.value)}
            required
          />
        </div>
        {createErr && <p className="text-xs text-red-400">{createErr}</p>}
        <button
          type="submit"
          className="rounded border border-slate-600 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-800"
        >
          Create plan
        </button>
      </form>
    </section>
  );
}

export default function AdminDesktopLicensingPage() {
  const nav = useNavigate();
  const [products, setProducts] = useState<DesktopProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [disabled, setDisabled] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const t = localStorage.getItem("fir_admin_token");
    if (!t) {
      nav("/login");
      return;
    }
    let cancelled = false;
    (async () => {
      setLoading(true);
      setLoadErr(null);
      setDisabled(false);
      try {
        const rows = await apiFetch<DesktopProduct[]>("/api/admin/desktop/products", { token: "admin" });
        if (!cancelled) setProducts(rows);
      } catch (ex) {
        const msg = ex instanceof Error ? ex.message : "Failed to load";
        if (!cancelled) {
          if (/404|Not found/i.test(msg)) {
            setDisabled(true);
            setProducts([]);
          } else if (/401|403|Unauthorized|admin/i.test(msg)) {
            localStorage.removeItem("fir_admin_token");
            nav("/login");
            return;
          } else {
            setLoadErr(msg);
            setProducts([]);
          }
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [nav, tick]);

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-white">Desktop software catalog</h1>
        <Link to="/admin" className="text-sm text-brand-500 hover:underline">
          ← Admin home
        </Link>
      </div>
      <p className="text-sm text-slate-400">
        Manage QR Code, ASN PDF Printer, and ASN Auto Filler product listings and annual seat prices.
        Requires <code className="text-slate-300">ENABLE_DESKTOP_LICENSING=true</code> on the API. Each plan is one
        seat / one key — not a shared multi-device license.
      </p>

      {loading && <p className="text-sm text-slate-500">Loading desktop catalog…</p>}
      {disabled && (
        <p className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-4 py-3 text-sm text-amber-100">
          Desktop licensing is disabled on this API (<code className="text-amber-50">ENABLE_DESKTOP_LICENSING</code>
          ). Turn the flag on to manage catalog and pricing.
        </p>
      )}
      {loadErr && <p className="text-sm text-red-400">{loadErr}</p>}
      {!loading && !disabled && !loadErr && products.length === 0 && (
        <p className="text-sm text-slate-400">
          No desktop products found. Ensure migration <code className="text-slate-300">032_desktop_licensing.sql</code>{" "}
          has been applied.
        </p>
      )}

      <div className="space-y-6">
        {products.map((p) => (
          <ProductCard key={p.id} product={p} onSaved={() => setTick((x) => x + 1)} />
        ))}
      </div>
    </div>
  );
}
