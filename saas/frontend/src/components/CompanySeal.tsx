/** Two-ring TheAIQualisys company seal (preview; PDF is drawn in the backend). */
export default function CompanySeal({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 120 120" className={className} aria-hidden="true">
      <defs>
        <path id="taq-seal-top" d="M 18,60 A 42,42 0 0 1 102,60" fill="none" />
        <path id="taq-seal-bot" d="M 18,60 A 42,42 0 0 0 102,60" fill="none" />
      </defs>
      <circle cx="60" cy="60" r="56" fill="none" stroke="#b03030" strokeWidth="3.2" />
      <circle cx="60" cy="60" r="32" fill="none" stroke="#b03030" strokeWidth="2.5" />
      <text
        fill="#b03030"
        fontFamily="Times New Roman, Times, serif"
        fontWeight="700"
        fontSize="11"
        letterSpacing="1.4"
      >
        <textPath href="#taq-seal-top" startOffset="50%" textAnchor="middle">
          TheAIQualisys
        </textPath>
      </text>
      <text
        fill="#b03030"
        fontFamily="Times New Roman, Times, serif"
        fontWeight="700"
        fontSize="8.5"
        letterSpacing="0.8"
      >
        <textPath href="#taq-seal-bot" startOffset="50%" textAnchor="middle">
          Bangalore-560090
        </textPath>
      </text>
      <circle cx="18" cy="60" r="2.2" fill="#b03030" />
      <circle cx="102" cy="60" r="2.2" fill="#b03030" />
    </svg>
  );
}
