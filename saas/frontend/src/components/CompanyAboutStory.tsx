/** Long-form company narrative — guest About route (`/pricing`) only; not on the home page. */
export default function CompanyAboutStory() {
  const sectionTitle = "text-xl font-semibold tracking-tight text-slate-900";
  const sectionCard = "space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6";

  return (
    <div className="space-y-6 text-slate-700">
      <section className={sectionCard}>
        <p>
          At TheAIQualisys, we believe that manufacturing excellence should not be limited by paperwork.
        </p>
        <p>
          Today, quality teams spend a significant amount of time handling documentation—FIRs, RCAs, PPAPs,
          audits—leaving less time for what truly matters: improving the product itself.
        </p>
        <p className="font-semibold text-slate-900">We are changing that.</p>
      </section>

      <section className={sectionCard}>
        <h2 className={sectionTitle}>Our Vision</h2>
        <p>To build a future where:</p>
        <p className="text-lg font-semibold text-slate-900">
          AI takes care of documentation, and humans focus on quality, precision, and innovation.
        </p>
      </section>

      <section className={sectionCard}>
        <h2 className={sectionTitle}>What We Do</h2>
        <p>We develop an AI-powered Quality Management System that:</p>
        <ul className="list-inside list-disc space-y-2 pl-1">
          <li>Automates FIR, RC2A, PPAP, and IATF documentation</li>
          <li>Reduces manual effort and human error</li>
          <li>Provides real-time insights for better decision-making</li>
          <li>Ensures audit-ready systems at all times</li>
        </ul>
      </section>

      <section className={sectionCard}>
        <h2 className={sectionTitle}>Our Philosophy</h2>
        <p>We strongly believe:</p>
        <blockquote className="rounded-r-xl border-l-4 border-brand-500/70 bg-brand-50/60 pl-4 py-2 italic text-slate-700">
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

      <section className={sectionCard}>
        <h2 className={sectionTitle}>Why We Exist</h2>
        <p>
          Because quality is not just about reports — it’s about delivering perfect parts, every time.
        </p>
      </section>

      <section className={sectionCard}>
        <h2 className={sectionTitle}>Our Mission</h2>
        <p>To empower manufacturing teams with intelligent systems that:</p>
        <ul className="list-inside list-disc space-y-2 pl-1">
          <li>Eliminate documentation burden</li>
          <li>Enhance decision-making</li>
          <li>Drive zero-defect manufacturing</li>
        </ul>
      </section>

      <section className={sectionCard}>
        <h2 className={sectionTitle}>The Future We Are Building</h2>
        <p>A connected quality ecosystem where:</p>
        <ul className="list-inside list-disc space-y-2 pl-1">
          <li>Every defect is tracked intelligently</li>
          <li>Every root cause is understood faster</li>
          <li>Every process continuously improves</li>
        </ul>
      </section>

      <p className="rounded-2xl border border-brand-100 bg-brand-50/70 p-5 text-base font-semibold leading-relaxed text-slate-900 sm:p-6">
        TheAIQualisys is not just software. It is the operating system for modern manufacturing quality.
      </p>
    </div>
  );
}
