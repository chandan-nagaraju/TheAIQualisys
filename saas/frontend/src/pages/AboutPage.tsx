import { Link } from "react-router-dom";
import CompanyAboutStory from "../components/CompanyAboutStory";

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-10">
      <div>
        <p className="text-sm font-medium uppercase tracking-[0.2em] text-brand-500">About</p>
        <h1 className="mt-3 text-4xl font-bold tracking-tight text-white">TheAIQualisys</h1>
      </div>

      <CompanyAboutStory />

      <section className="flex flex-wrap gap-4 border-t border-slate-800 pt-10">
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
