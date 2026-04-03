export type QmsModuleSlug = "drawings" | "rc2a" | "ppap" | "iatf";

export type QmsModuleDef = {
  slug: QmsModuleSlug;
  /** Matches `module_pricing.module_name` / backend. */
  moduleName: string;
  title: string;
  shortDescription: string;
  landingStatus: "available" | "development";
  features: string[];
};

export const QMS_MODULES: QmsModuleDef[] = [
  {
    slug: "drawings",
    moduleName: "drawings_directory",
    title: "Drawings Directory",
    shortDescription: "Central drawing index, revisions, and plant-wide search.",
    landingStatus: "development",
    features: [
      "Drawing metadata and revision tracking",
      "Full-text and part-number search",
      "Role-based access for engineering and quality",
    ],
  },
  {
    slug: "rc2a",
    moduleName: "rc2a",
    title: "RC2A",
    shortDescription: "Repeatable corrective action workflows aligned to your QMS.",
    landingStatus: "development",
    features: ["8D / RCA templates", "Action tracking and sign-off", "Audit trail"],
  },
  {
    slug: "ppap",
    moduleName: "ppap",
    title: "PPAP",
    shortDescription: "Production Part Approval Process packs and submission tracking.",
    landingStatus: "development",
    features: ["PSW and element checklists", "Document bundling", "Customer submission status"],
  },
  {
    slug: "iatf",
    moduleName: "iatf_documentation",
    title: "IATF Documentation",
    shortDescription: "IATF 16949 evidence, process maps, and audit-ready folders.",
    landingStatus: "development",
    features: ["Clause mapping", "Controlled documents", "Management review records"],
  },
];

export function getModuleBySlug(slug: string): QmsModuleDef | undefined {
  return QMS_MODULES.find((m) => m.slug === slug);
}
