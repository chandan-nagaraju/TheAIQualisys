import { Link } from "react-router-dom";
import CompanyAboutStory from "../components/CompanyAboutStory";

export default function AboutPage() {
  const highlights = [
    { label: "Documentation automated", value: "FIR, RCA, PPAP" },
    { label: "Built for manufacturing", value: "Audit-ready workflows" },
    { label: "Outcome focus", value: "Quality over paperwork" },
  ];

  return (
    <div className="mx-auto w-full max-w-5xl space-y-8">
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        <p className="inline-flex rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
          About
        </p>
        <h1 className="mt-4 text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">TheAIQualisys</h1>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-slate-600 sm:text-base">
          We are building the quality operating system for modern manufacturing teams - where AI handles repetitive
          documentation and people focus on precision, root-cause prevention, and continuous improvement.
        </p>
        <div className="mt-6 grid gap-3 sm:grid-cols-3">
          {highlights.map((item) => (
            <div key={item.label} className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{item.label}</p>
              <p className="mt-1 text-sm font-semibold text-slate-900">{item.value}</p>
            </div>
          ))}
        </div>
      </section>

      <CompanyAboutStory />

      <section className="flex flex-wrap gap-3 border-t border-slate-200 pt-8">
        <Link
          to="/pricing/all-modules"
          className="inline-flex min-h-11 items-center justify-center rounded-xl bg-brand-600 px-6 py-3 text-sm font-semibold text-white hover:bg-brand-500"
        >
          View module pricing
        </Link>
        <Link
          to="/signup"
          className="inline-flex min-h-11 items-center justify-center rounded-xl border border-slate-300 bg-white px-6 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50"
        >
          Get started
        </Link>
      </section>
    </div>
  );
}
