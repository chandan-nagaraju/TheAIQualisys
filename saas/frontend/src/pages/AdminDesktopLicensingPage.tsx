import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiFetch } from "../api";
import { sortPlansByDuration } from "../desktopCadence";

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

type PlanDraft = {
  name: string;
  code: string;
  price: string;
  duration: string;
};

function draftsFromPlans(plans: DesktopPlan[]): Record<number, PlanDraft> {
  const next: Record<number, PlanDraft> = {};
  for (const plan of plans) {
    next[plan.id] = {
      name: plan.name,
      code: plan.code,
      price: String(plan.price_inr),
      duration: String(plan.duration_days),
    };
  }
  return next;
}

function CadencePlansEditor({
  plans,
  onSaved,
}: {
  plans: DesktopPlan[];
  onSaved: () => void;
}) {
  const sorted = sortPlansByDuration(plans);
  const [drafts, setDrafts] = useState(() => draftsFromPlans(plans));
  const [status, setStatus] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setDrafts(draftsFromPlans(plans));
    setStatus(null);
    setErr(null);
  }, [plans]);

  function updateDraft(planId: number, patch: Partial<PlanDraft>) {
    setDrafts((prev) => ({
      ...prev,
      [planId]: { ...prev[planId], ...patch },
    }));
  }

  async function saveAll() {
    setErr(null);
    setStatus(null);
    setBusy(true);
    try {
      for (const plan of sorted) {
        const d = drafts[plan.id];
        if (!d) continue;
        await apiFetch(`/api/admin/desktop/plans/${plan.id}`, {
          method: "PATCH",
          token: "admin",
          body: JSON.stringify({
            name: d.name.trim(),
            code: d.code.trim(),
            price_inr: parseInt(d.price, 10),
            duration_days: parseInt(d.duration, 10),
          }),
        });
      }
      setStatus("Cadence saved.");
      onSaved();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto rounded-lg border border-slate-800">
        <div className="grid min-w-[36rem] grid-cols-[minmax(8rem,1.2fr)_minmax(10rem,1.3fr)_5.5rem_4.5rem] items-center gap-2 px-3 py-2">
          <span className="text-[11px] uppercase tracking-wide text-slate-500">Name</span>
          <span className="text-[11px] uppercase tracking-wide text-slate-500">Code</span>
          <span className="text-[11px] uppercase tracking-wide text-slate-500">Price ₹</span>
          <span className="text-[11px] uppercase tracking-wide text-slate-500">Days</span>
          {sorted.map((plan) => {
            const d = drafts[plan.id];
            if (!d) return null;
            return (
              <div key={plan.id} className="contents">
                <input
                  aria-label={`${plan.name} name`}
                  className="min-w-0 rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
                  value={d.name}
                  onChange={(e) => updateDraft(plan.id, { name: e.target.value })}
                />
                <input
                  aria-label={`${plan.name} code`}
                  className="min-w-0 rounded border border-slate-700 bg-slate-950 px-2 py-1.5 font-mono text-xs text-white"
                  value={d.code}
                  onChange={(e) => updateDraft(plan.id, { code: e.target.value })}
                />
                <input
                  aria-label={`${plan.name} price INR`}
                  type="number"
                  min={0}
                  className="min-w-0 rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
                  value={d.price}
                  onChange={(e) => updateDraft(plan.id, { price: e.target.value })}
                />
                <input
                  aria-label={`${plan.name} duration days`}
                  type="number"
                  min={1}
                  className="min-w-0 rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
                  value={d.duration}
                  onChange={(e) => updateDraft(plan.id, { duration: e.target.value })}
                />
              </div>
            );
          })}
        </div>
      </div>
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={busy}
          className="rounded bg-brand-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-500 disabled:opacity-50"
          onClick={() => void saveAll()}
        >
          {busy ? "Saving…" : "Save"}
        </button>
        {err ? <span className="text-xs text-red-400">{err}</span> : null}
        {status ? <span className="text-xs text-emerald-400">{status}</span> : null}
      </div>
    </div>
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
  const [newPrice, setNewPrice] = useState("499");
  const [newDuration, setNewDuration] = useState("30");
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
        <h3 className="text-sm font-semibold text-slate-200">Cadence (1 seat each)</h3>
        <p className="text-xs text-slate-500">
          Pulse → Season → Horizon → Orbit. Catalog visibility is the product listing above.
        </p>
        {product.plans.length > 0 ? (
          <CadencePlansEditor plans={product.plans} onSaved={onSaved} />
        ) : (
          <p className="text-xs text-slate-500">No plans yet — add one below.</p>
        )}
      </div>

      <form
        onSubmit={createPlan}
        className="grid gap-2 rounded-lg border border-dashed border-slate-700 p-3 sm:grid-cols-[minmax(8rem,1.2fr)_minmax(10rem,1.3fr)_5.5rem_4.5rem_auto] sm:items-end"
      >
        <label className="block text-xs text-slate-500">
          Name
          <input
            placeholder="Pulse · 1 seat"
            className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            required
          />
        </label>
        <label className="block text-xs text-slate-500">
          Code
          <input
            placeholder="QR_PULSE_1SEAT"
            className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 font-mono text-xs text-white"
            value={newCode}
            onChange={(e) => setNewCode(e.target.value)}
            required
          />
        </label>
        <label className="block text-xs text-slate-500">
          Price ₹
          <input
            type="number"
            min={0}
            className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
            value={newPrice}
            onChange={(e) => setNewPrice(e.target.value)}
            required
          />
        </label>
        <label className="block text-xs text-slate-500">
          Days
          <input
            type="number"
            min={1}
            className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-white"
            value={newDuration}
            onChange={(e) => setNewDuration(e.target.value)}
            required
          />
        </label>
        <div>
          {createErr && <p className="mb-1 text-xs text-red-400">{createErr}</p>}
          <button
            type="submit"
            className="rounded border border-slate-600 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-800"
          >
            Add
          </button>
        </div>
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
        Cadence™ plans are Pulse (30d), Season (90d), Horizon (180d), and Orbit (365d) — one seat / one key each.
        Codes follow <code className="text-slate-300">{"{PREFIX}_PULSE_1SEAT"}</code> (QR, ASN_PDF, ASN_FILL). Requires{" "}
        <code className="text-slate-300">ENABLE_DESKTOP_LICENSING=true</code> on the API.
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
