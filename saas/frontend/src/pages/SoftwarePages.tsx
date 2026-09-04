import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiFetch } from "../api";

type Plan = {
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

type Product = {
  id: number;
  code: string;
  name: string;
  description: string | null;
  listing_active: boolean;
  plans: Plan[];
};

type CheckoutContext = {
  user_id: number;
  email: string;
  company_id: number;
  company_name: string;
};

export type DesktopOrder = {
  id: number;
  order_number: string;
  company_id: number;
  user_id: number;
  product_id: number;
  plan_id: number;
  product_code: string;
  product_name: string;
  plan_code: string;
  plan_name: string;
  duration_days: number;
  seats: number;
  unit_price_inr: number;
  total_price_inr: number;
  currency: string;
  status: string;
  created_at: string | null;
};

function statusLabel(status: string): string {
  if (status === "pending_payment") return "Pending payment";
  if (status === "payment_submitted") return "Payment submitted";
  if (status === "approved") return "Approved";
  if (status === "rejected") return "Rejected";
  if (status === "cancelled") return "Cancelled";
  return status;
}

function inr(n: number): string {
  return `₹${n.toLocaleString("en-IN")}`;
}

/** Software catalog */
export function SoftwareCatalogPage() {
  const nav = useNavigate();
  const [products, setProducts] = useState<Product[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [disabled, setDisabled] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!localStorage.getItem("fir_token")) {
      nav("/login");
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const rows = await apiFetch<Product[]>("/api/desktop/products");
        if (!cancelled) setProducts(rows);
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Failed to load";
        if (!cancelled) {
          if (/404|Not found/i.test(msg)) setDisabled(true);
          else setErr(msg);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [nav]);

  return (
    <div className="mx-auto max-w-4xl space-y-8 px-4 py-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-white">Software</h1>
        <Link to="/software/orders" className="text-sm text-brand-500 hover:underline">
          My orders
        </Link>
      </div>
      <p className="text-sm text-slate-400">
        Desktop applications for Windows. Each seat is one independent license for one PC (keys are issued after
        payment is approved — Phase 4).
      </p>
      {loading && <p className="text-sm text-slate-500">Loading catalog…</p>}
      {disabled && (
        <p className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-4 py-3 text-sm text-amber-100">
          Desktop software purchasing is not enabled on this environment yet.
        </p>
      )}
      {err && <p className="text-sm text-red-400">{err}</p>}
      <div className="space-y-4">
        {products.map((p) => {
          const from = p.plans.length ? Math.min(...p.plans.map((pl) => pl.price_inr)) : null;
          return (
            <div
              key={p.id}
              className="flex flex-col gap-3 rounded-xl border border-slate-800 bg-slate-900/50 p-5 sm:flex-row sm:items-center sm:justify-between"
            >
              <div>
                <h2 className="text-lg font-semibold text-white">{p.name}</h2>
                <p className="mt-1 text-sm text-slate-400">{p.description || p.code}</p>
                {from != null && (
                  <p className="mt-2 text-sm text-slate-300">From {inr(from)} / seat / year</p>
                )}
              </div>
              <Link
                to={`/software/${encodeURIComponent(p.code)}`}
                className="inline-flex shrink-0 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-500"
              >
                Select plan
              </Link>
            </div>
          );
        })}
      </div>
      {!loading && !disabled && !err && products.length === 0 && (
        <p className="text-sm text-slate-400">No desktop products are listed yet.</p>
      )}
    </div>
  );
}

/** Product → plan → seats → checkout confirm */
export function SoftwareProductPage() {
  const { productCode = "" } = useParams();
  const nav = useNavigate();
  const [product, setProduct] = useState<Product | null>(null);
  const [planId, setPlanId] = useState<number | null>(null);
  const [seats, setSeats] = useState("1");
  const [ctx, setCtx] = useState<CheckoutContext | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState<"plan" | "confirm">("plan");

  useEffect(() => {
    if (!localStorage.getItem("fir_token")) {
      nav("/login");
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const [rows, checkout] = await Promise.all([
          apiFetch<Product[]>("/api/desktop/products"),
          apiFetch<CheckoutContext>("/api/desktop/checkout-context"),
        ]);
        if (cancelled) return;
        const p = rows.find((r) => r.code === productCode) || null;
        setProduct(p);
        setCtx(checkout);
        if (p?.plans[0]) setPlanId(p.plans[0].id);
      } catch (e) {
        if (!cancelled) setErr(e instanceof Error ? e.message : "Failed to load");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [nav, productCode]);

  const plan = useMemo(
    () => product?.plans.find((pl) => pl.id === planId) || null,
    [product, planId],
  );
  const seatN = Math.max(1, parseInt(seats, 10) || 1);
  const total = plan ? plan.price_inr * seatN : 0;

  async function placeOrder(e: FormEvent) {
    e.preventDefault();
    if (!product || !plan) return;
    setBusy(true);
    setErr(null);
    try {
      const order = await apiFetch<DesktopOrder>("/api/desktop/orders", {
        method: "POST",
        body: JSON.stringify({
          product_id: product.id,
          plan_id: plan.id,
          seats: seatN,
        }),
      });
      nav(`/software/orders/${order.id}`);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Could not create order");
    } finally {
      setBusy(false);
    }
  }

  if (err && !product) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-10">
        <p className="text-sm text-red-400">{err}</p>
        <Link to="/software" className="mt-4 inline-block text-sm text-brand-500">
          ← Software
        </Link>
      </div>
    );
  }

  if (!product) {
    return <p className="px-4 py-10 text-sm text-slate-500">Loading…</p>;
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6 px-4 py-10">
      <Link to="/software" className="text-sm text-brand-500 hover:underline">
        ← Software
      </Link>
      <h1 className="text-2xl font-semibold text-white">{product.name}</h1>
      <p className="text-sm text-slate-400">{product.description}</p>

      {step === "plan" && (
        <div className="space-y-4 rounded-xl border border-slate-800 bg-slate-900/50 p-5">
          <h2 className="text-sm font-semibold text-slate-200">Select plan</h2>
          <div className="space-y-2">
            {product.plans.map((pl) => (
              <label
                key={pl.id}
                className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 ${
                  planId === pl.id ? "border-brand-500 bg-brand-950/30" : "border-slate-700"
                }`}
              >
                <input
                  type="radio"
                  name="plan"
                  checked={planId === pl.id}
                  onChange={() => setPlanId(pl.id)}
                  className="mt-1"
                />
                <span>
                  <span className="block font-medium text-white">{pl.name}</span>
                  <span className="text-sm text-slate-400">
                    {inr(pl.price_inr)} / seat · {pl.duration_days} days · 1 seat = 1 PC
                  </span>
                </span>
              </label>
            ))}
          </div>
          <label className="block text-xs text-slate-500">
            Number of seats
            <input
              type="number"
              min={1}
              max={500}
              className="mt-1 w-full max-w-xs rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
              value={seats}
              onChange={(e) => setSeats(e.target.value)}
            />
          </label>
          {plan && (
            <p className="text-sm text-slate-300">
              {seatN} × {inr(plan.price_inr)} = <strong className="text-white">{inr(total)}</strong>
            </p>
          )}
          <button
            type="button"
            disabled={!plan}
            onClick={() => setStep("confirm")}
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-500 disabled:opacity-40"
          >
            Continue to confirm
          </button>
        </div>
      )}

      {step === "confirm" && plan && ctx && (
        <form onSubmit={placeOrder} className="space-y-4 rounded-xl border border-slate-800 bg-slate-900/50 p-5">
          <h2 className="text-sm font-semibold text-slate-200">Confirm order</h2>
          <dl className="grid gap-2 text-sm text-slate-300 sm:grid-cols-2">
            <div>
              <dt className="text-xs text-slate-500">Product</dt>
              <dd className="text-white">{product.name}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Plan</dt>
              <dd className="text-white">{plan.name}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Seats</dt>
              <dd className="text-white">{seatN}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Price per seat</dt>
              <dd className="text-white">{inr(plan.price_inr)}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Total</dt>
              <dd className="text-lg font-semibold text-white">{inr(total)}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Company</dt>
              <dd className="text-white">{ctx.company_name}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-xs text-slate-500">Account email</dt>
              <dd className="text-white">{ctx.email}</dd>
            </div>
          </dl>
          <p className="text-xs text-slate-500">
            Creating this order does not charge you and does not issue license keys yet. Status will be{" "}
            <strong className="text-slate-300">Pending payment</strong> until you complete UPI payment in a later step.
          </p>
          {err && <p className="text-sm text-red-400">{err}</p>}
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setStep("plan")}
              className="rounded-lg border border-slate-600 px-4 py-2 text-sm text-slate-200"
            >
              Back
            </button>
            <button
              type="submit"
              disabled={busy}
              className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-500 disabled:opacity-50"
            >
              {busy ? "Creating…" : "Create order"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

export function SoftwareOrdersPage() {
  const nav = useNavigate();
  const [orders, setOrders] = useState<DesktopOrder[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!localStorage.getItem("fir_token")) {
      nav("/login");
      return;
    }
    (async () => {
      try {
        setOrders(await apiFetch<DesktopOrder[]>("/api/desktop/orders"));
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Failed to load orders");
      }
    })();
  }, [nav]);

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-white">My software orders</h1>
        <Link to="/software" className="text-sm text-brand-500 hover:underline">
          ← Software
        </Link>
      </div>
      {err && <p className="text-sm text-red-400">{err}</p>}
      <div className="space-y-3">
        {orders.map((o) => (
          <Link
            key={o.id}
            to={`/software/orders/${o.id}`}
            className="block rounded-xl border border-slate-800 bg-slate-900/50 p-4 hover:border-slate-600"
          >
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="font-mono text-sm text-brand-400">{o.order_number}</span>
              <span className="text-xs text-slate-400">{statusLabel(o.status)}</span>
            </div>
            <p className="mt-1 text-sm text-white">
              {o.product_name} · {o.plan_name}
            </p>
            <p className="text-xs text-slate-400">
              {o.seats} seat{o.seats === 1 ? "" : "s"} · {inr(o.total_price_inr)}
            </p>
          </Link>
        ))}
      </div>
      {!err && orders.length === 0 && (
        <p className="text-sm text-slate-400">No orders yet. Start from the Software catalog.</p>
      )}
    </div>
  );
}

export function SoftwareOrderDetailPage() {
  const { orderId } = useParams();
  const nav = useNavigate();
  const [order, setOrder] = useState<DesktopOrder | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!localStorage.getItem("fir_token")) {
      nav("/login");
      return;
    }
    const id = parseInt(orderId || "", 10);
    if (!id) {
      setErr("Invalid order");
      return;
    }
    (async () => {
      try {
        setOrder(await apiFetch<DesktopOrder>(`/api/desktop/orders/${id}`));
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Order not found");
      }
    })();
  }, [nav, orderId]);

  if (err) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-10">
        <p className="text-sm text-red-400">{err}</p>
        <Link to="/software/orders" className="mt-4 inline-block text-sm text-brand-500">
          ← My orders
        </Link>
      </div>
    );
  }
  if (!order) return <p className="px-4 py-10 text-sm text-slate-500">Loading…</p>;

  return (
    <div className="mx-auto max-w-2xl space-y-6 px-4 py-10">
      <Link to="/software/orders" className="text-sm text-brand-500 hover:underline">
        ← My orders
      </Link>
      <h1 className="text-2xl font-semibold text-white">Order confirmation</h1>
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-5 space-y-3">
        <p className="font-mono text-lg text-brand-400">{order.order_number}</p>
        <p className="text-sm text-slate-300">
          Status: <strong className="text-white">{statusLabel(order.status)}</strong>
        </p>
        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs text-slate-500">Product</dt>
            <dd className="text-white">{order.product_name}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Plan</dt>
            <dd className="text-white">{order.plan_name}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Seats</dt>
            <dd className="text-white">{order.seats}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Price per seat</dt>
            <dd className="text-white">{inr(order.unit_price_inr)}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Total</dt>
            <dd className="text-lg font-semibold text-white">{inr(order.total_price_inr)}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Term</dt>
            <dd className="text-white">{order.duration_days} days</dd>
          </div>
        </dl>
        <p className="text-xs text-slate-500">
          License keys are not issued at this step. Payment instructions will be available in a later release (Phase 4).
        </p>
      </div>
    </div>
  );
}
