/** Long-form company narrative — guest About route (`/pricing`) only; not on the home page. */
export default function CompanyAboutStory() {
  return (
    <div className="mx-auto max-w-3xl space-y-10 text-slate-300">
      <section className="space-y-4">
        <p>
          At TheAIQualisys, we believe that manufacturing excellence should not be limited by paperwork.
        </p>
        <p>
          Today, quality teams spend a significant amount of time handling documentation—FIRs, RCAs, PPAPs,
          audits—leaving less time for what truly matters: improving the product itself.
        </p>
        <p className="font-medium text-slate-200">We are changing that.</p>
      </section>

      <hr className="border-slate-800" />

      <section className="space-y-4">
        <h2 className="text-xl font-semibold text-white">Our Vision</h2>
        <p>To build a future where:</p>
        <p className="text-lg font-semibold text-slate-100">
          AI takes care of documentation, and humans focus on quality, precision, and innovation.
        </p>
      </section>

      <hr className="border-slate-800" />

      <section className="space-y-4">
        <h2 className="text-xl font-semibold text-white">What We Do</h2>
        <p>We develop an AI-powered Quality Management System that:</p>
        <ul className="list-inside list-disc space-y-2 pl-1">
          <li>Automates FIR, RC2A, PPAP, and IATF documentation</li>
          <li>Reduces manual effort and human error</li>
          <li>Provides real-time insights for better decision-making</li>
          <li>Ensures audit-ready systems at all times</li>
        </ul>
      </section>

      <hr className="border-slate-800" />

      <section className="space-y-4">
        <h2 className="text-xl font-semibold text-white">Our Philosophy</h2>
        <p>We strongly believe:</p>
        <blockquote className="border-l-4 border-brand-500/60 pl-4 italic text-slate-400">
          “Machines should handle repetitive work. Humans should create value.”
        </blockquote>
        <p>By automating documentation through AI, we enable engineers and operators to:</p>
        <ul className="list-inside list-disc space-y-2 pl-1">
          <li>Spend more time on improving part quality</li>
          <li>Reduce defects at the source</li>
          <li>Increase productivity on the shop floor</li>
          <li>Focus on continuous improvement</li>
        </ul>
      </section>

      <hr className="border-slate-800" />

      <section className="space-y-3">
        <h2 className="text-xl font-semibold text-white">Why We Exist</h2>
        <p>
          Because quality is not just about reports — it’s about delivering perfect parts, every time.
        </p>
      </section>

      <hr className="border-slate-800" />

      <section className="space-y-4">
        <h2 className="text-xl font-semibold text-white">Our Mission</h2>
        <p>To empower manufacturing teams with intelligent systems that:</p>
        <ul className="list-inside list-disc space-y-2 pl-1">
          <li>Eliminate documentation burden</li>
          <li>Enhance decision-making</li>
          <li>Drive zero-defect manufacturing</li>
        </ul>
      </section>

      <hr className="border-slate-800" />

      <section className="space-y-4">
        <h2 className="text-xl font-semibold text-white">The Future We Are Building</h2>
        <p>A connected quality ecosystem where:</p>
        <ul className="list-inside list-disc space-y-2 pl-1">
          <li>Every defect is tracked intelligently</li>
          <li>Every root cause is understood faster</li>
          <li>Every process continuously improves</li>
        </ul>
      </section>

      <p className="pt-2 text-base font-semibold leading-relaxed text-slate-100">
        TheAIQualisys is not just software. It is the operating system for modern manufacturing quality.
      </p>
    </div>
  );
}
