/**
 * Vector brand: circuit-style Q (+ optional TheAIQualisys wordmark). SVG uses currentColor.
 */
type BrandLogoProps = {
  className?: string;
  size?: "md" | "lg";
  /** When false, only the Q mark (for compact headers, e.g. FIR workspace). */
  wordmark?: boolean;
};

function QMarkIcon({ size }: { size: "md" | "lg" }) {
  const iconBox = size === "lg" ? "h-12 w-12 sm:h-14 sm:w-14" : "h-8 w-8 sm:h-9 sm:w-9";
  return (
    <svg
      className={`shrink-0 ${iconBox}`}
      viewBox="0 0 64 56"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <circle cx="7" cy="17" r="2.5" fill="currentColor" />
      <path
        d="M10 17h12M7 28h14M7 39h11"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      <circle cx="7" cy="28" r="2.5" fill="currentColor" />
      <circle cx="7" cy="39" r="2.5" fill="currentColor" />
      <path
        fill="currentColor"
        fillRule="evenodd"
        clipRule="evenodd"
        d="M38 9a17 17 0 1 1 0 34 17 17 0 0 1 0-34zm0 9a8 8 0 1 0 0 16 8 8 0 0 0 0-16zm7.5 19.5l14 16.5h-9l-9-10.5a17 17 0 0 0 4-6z"
      />
    </svg>
  );
}

export default function BrandLogo({ className = "", size = "md", wordmark = true }: BrandLogoProps) {
  const textClass =
    size === "lg"
      ? "text-xl font-bold tracking-tight sm:text-2xl"
      : "text-lg font-bold tracking-tight";

  if (!wordmark) {
    return (
      <span className={`inline-flex items-center ${className}`}>
        <QMarkIcon size={size} />
      </span>
    );
  }

  return (
    <span className={`inline-flex items-center gap-2 sm:gap-2.5 ${className}`}>
      <QMarkIcon size={size} />
      <span className={`leading-none select-none ${textClass}`}>TheAIQualisys</span>
    </span>
  );
}
