import { useMemo } from "react";
import { QMS_MODULES } from "../moduleCatalog";

export type UpgradeInfo = { upi_id: string; whatsapp_url: string; message: string };
export type PlanInfo = { plan_type: string; name: string; price_inr: number };

export const QR_REFRESH_MS = 60_000;

export const BILLING_OPTIONS = [
  { id: "1m" as const, label: "Month" },
  { id: "3m" as const, label: "Quarterly" },
  { id: "6m" as const, label: "Half yearly" },
  { id: "12m" as const, label: "Yearly" },
] as const;

export type BillingId = (typeof BILLING_OPTIONS)[number]["id"];

export function isEnterprisePlan(planType: string, planName: string): boolean {
  const t = planType.trim().toLowerCase();
  const n = planName.trim().toLowerCase();
  return t === "enterprise" || n.includes("enterprise");
}

export function billingTotalInr(monthly: number, id: BillingId, enterprise: boolean): number {
  switch (id) {
    case "1m":
      return monthly;
    case "3m":
      return monthly * 3;
    case "6m":
      return enterprise ? Math.round(monthly * 6 - monthly / 2) : monthly * 6;
    case "12m":
      return monthly * 11;
    default:
      return monthly;
  }
}

const BILLING_IDS: BillingId[] = ["1m", "3m", "6m", "12m"];

export function parseBillingId(raw: string | null): BillingId | null {
  if (!raw) return null;
  const s = raw.trim().toLowerCase();
  return BILLING_IDS.includes(s as BillingId) ? (s as BillingId) : null;
}

export function billingPeriodApi(id: BillingId): "MONTHLY" | "QUARTERLY" | "HALF_YEARLY" | "YEARLY" {
  if (id === "3m") return "QUARTERLY";
  if (id === "6m") return "HALF_YEARLY";
  if (id === "12m") return "YEARLY";
  return "MONTHLY";
}

export function moduleKeyFromSearch(search: string): string {
  const q = new URLSearchParams(search);
  return (q.get("module") || q.get("module_key") || "fir").trim() || "fir";
}

export function moduleDisplayName(moduleKey: string, fallback = "FIR"): string {
  const key = (moduleKey || "fir").trim().toLowerCase();
  if (!key || key === "fir" || key === "final_inspection") return "FIR";
  const def = QMS_MODULES.find((m) => m.moduleName.toLowerCase() === key || m.slug === key);
  return def?.title || fallback;
}

export function buildUpgradeSearch(opts: {
  moduleKey?: string;
  planName: string;
  planType: string;
  priceInr: number;
}): string {
  const q = new URLSearchParams();
  q.set("module", opts.moduleKey || "fir");
  q.set("plan_name", opts.planName);
  q.set("plan_type", opts.planType);
  q.set("price_inr", String(opts.priceInr));
  return q.toString();
}

export type SelectedPlan = {
  planName: string;
  planType: string;
  price: number | null;
} | null;

export function useSelectedPlan(plans: PlanInfo[]): SelectedPlan {
  return useMemo(() => {
    const q = new URLSearchParams(window.location.search);
    const planName = (q.get("plan_name") || q.get("plan") || "").trim();
    const planType = (q.get("plan_type") || "").trim();
    const priceRaw = (
      q.get("price_inr") ||
      q.get("price_in") ||
      q.get("price") ||
      q.get("rate") ||
      ""
    ).trim();
    const price = /^\d+$/.test(priceRaw) ? Number(priceRaw) : null;
    const planTypeNorm = planType.toLowerCase();
    const planNameNorm = planName.toLowerCase();
    const matched = plans.find(
      (p) =>
        (planTypeNorm && p.plan_type.toLowerCase() === planTypeNorm) ||
        (planNameNorm && p.name.toLowerCase() === planNameNorm),
    );
    if (!planName && !planType && price == null && !matched) return null;
    return {
      planName: planName || matched?.name || "Selected plan",
      planType: planType || matched?.plan_type || "",
      price: price ?? matched?.price_inr ?? null,
    };
  }, [plans]);
}
