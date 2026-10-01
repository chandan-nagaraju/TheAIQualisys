/** TheAIQualisys Cadence™ — same four tiers on every desktop product. */

export type CadenceSlug = "PULSE" | "SEASON" | "HORIZON" | "ORBIT";

export const CADENCE_CATALOG_LINE = "Choose your cadence: Pulse → Season → Horizon → Orbit";

const BY_SLUG: Record<
  CadenceSlug,
  { badge: string; days: number; tagline: string; savings: string | null; bestValue: boolean }
> = {
  PULSE: {
    badge: "30d",
    days: 30,
    tagline: "Month by month — stay in sync",
    savings: null,
    bestValue: false,
  },
  SEASON: {
    badge: "90d",
    days: 90,
    tagline: "One quarter of uninterrupted use",
    savings: "Save vs 3× Pulse",
    bestValue: false,
  },
  HORIZON: {
    badge: "180d",
    days: 180,
    tagline: "Six months locked to your machine",
    savings: "Save vs 6× Pulse",
    bestValue: false,
  },
  ORBIT: {
    badge: "365d",
    days: 365,
    tagline: "Full year around your workflow",
    savings: "Best value — full year",
    bestValue: true,
  },
};

export function cadenceSlugFromPlan(code: string, durationDays: number): CadenceSlug | null {
  const u = (code || "").toUpperCase();
  if (u.includes("_PULSE_")) return "PULSE";
  if (u.includes("_SEASON_")) return "SEASON";
  if (u.includes("_HORIZON_")) return "HORIZON";
  if (u.includes("_ORBIT_") || u === "ANNUAL_1SEAT") return "ORBIT";
  if (durationDays <= 45) return "PULSE";
  if (durationDays <= 120) return "SEASON";
  if (durationDays <= 200) return "HORIZON";
  if (durationDays >= 300) return "ORBIT";
  return null;
}

export function cadenceMeta(code: string, durationDays: number) {
  const slug = cadenceSlugFromPlan(code, durationDays);
  if (!slug) {
    return {
      badge: `${durationDays}d`,
      tagline: null as string | null,
      savings: null as string | null,
      bestValue: false,
      slug: null as CadenceSlug | null,
    };
  }
  const t = BY_SLUG[slug];
  return { badge: t.badge, tagline: t.tagline, savings: t.savings, bestValue: t.bestValue, slug };
}

export function sortPlansByDuration<T extends { duration_days: number; sort_order?: number; id: number }>(
  plans: T[],
): T[] {
  return [...plans].sort(
    (a, b) => a.duration_days - b.duration_days || (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.id - b.id,
  );
}
