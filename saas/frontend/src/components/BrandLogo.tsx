/**
 * Vector brand: circuit-style Q (+ optional TheAIQualisys wordmark).
 * Icon paths match the master SVG Q group; wordmark is HTML for responsive typography.
 * Icon box uses 1em so height matches the wordmark font size on the same flex row.
 */
type BrandLogoProps = {
  className?: string;
  size?: "md" | "lg";
  /** When false, only the Q mark (for compact headers, e.g. FIR workspace). */
  wordmark?: boolean;
};

/** Q icon from brand master (stroke ring, tail, circuit lines); size via parent `font-size` + `h-[1em] w-[1em]`. */
function QMarkIcon({ className }: { className?: string }) {
  return (
    <svg
      className={`h-[1em] w-[1em] shrink-0 ${className ?? ""}`}
      viewBox="0 0 140 140"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <g transform="translate(20, 20)" stroke="currentColor" fill="currentColor">
        <circle cx="60" cy="60" r="50" strokeWidth="10" fill="none" />
        <line x1="90" y1="90" x2="115" y2="115" strokeWidth="10" strokeLinecap="round" />
        <line x1="10" y1="45" x2="55" y2="45" strokeWidth="6" strokeLinecap="round" />
        <circle cx="55" cy="45" r="4" />
        <line x1="10" y1="60" x2="40" y2="60" strokeWidth="6" strokeLinecap="round" />
        <circle cx="40" cy="60" r="4" />
        <line x1="10" y1="75" x2="50" y2="75" strokeWidth="6" strokeLinecap="round" />
        <circle cx="50" cy="75" r="4" />
      </g>
    </svg>
  );
}

export default function BrandLogo({ className = "", size = "md", wordmark = true }: BrandLogoProps) {
  const textClass =
    size === "lg"
      ? "text-xl font-bold tracking-tight sm:text-2xl"
      : "text-lg font-bold tracking-tight";

  if (!wordmark) {
    const shellClass =
      size === "lg"
        ? `inline-flex items-center text-xl font-bold sm:text-2xl ${className}`
        : `inline-flex items-center text-base font-semibold sm:text-lg ${className}`;
    return (
      <span className={shellClass}>
        <QMarkIcon />
      </span>
    );
  }

  return (
    <span className={`inline-flex items-center gap-2 sm:gap-2.5 ${textClass} ${className}`}>
      <QMarkIcon />
      <span className="leading-none select-none">TheAIQualisys</span>
    </span>
  );
}
