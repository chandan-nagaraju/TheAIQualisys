import { Link } from "react-router-dom";

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-10">
      <div>
        <p className="text-sm font-medium uppercase tracking-[0.2em] text-brand-500">About</p>
        <h1 className="mt-3 text-4xl font-bold tracking-tight text-white">TheAIQualisys</h1>
        <p className="mt-4 text-lg text-slate-400">
          An AI-powered quality management platform for manufacturing teams — automate FIR documentation today and grow
          into RC2A, PPAP, IATF, and drawing workflows as modules ship.
        </p>
      </div>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6">
        <h2 className="text-lg font-semibold text-white">What we offer</h2>
        <ul className="mt-4 list-inside list-disc space-y-2 text-sm text-slate-300">
          <li>
            <strong className="text-slate-200">FIR Automation</strong> — production-ready: invoices, inspection, part
            master, printable final inspection reports.
          </li>
          <li>
            <strong className="text-slate-200">More modules</strong> — Drawings directory, RC2A, PPAP, and IATF
            documentation are in active development with trial access for early adopters.
          </li>
        </ul>
      </section>

      <section className="flex flex-wrap gap-4">
        <Link
          to="/pricing/all-modules"
          className="inline-flex rounded-xl bg-brand-600 px-6 py-3 text-sm font-semibold text-white hover:bg-brand-500"
        >
          View module pricing
        </Link>
        <Link
          to="/signup"
          className="inline-flex rounded-xl border border-slate-600 px-6 py-3 text-sm font-semibold text-slate-200 hover:border-slate-500"
        >
          Get started
        </Link>
      </section>
    </div>
  );
}
