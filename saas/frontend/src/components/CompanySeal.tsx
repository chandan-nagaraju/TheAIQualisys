/** Two-ring TheAIQualisys company seal with the signatory name in the centre. */
export default function CompanySeal({
  className,
  name,
}: {
  className?: string;
  name?: string;
}) {
  const label = (name || "").trim();
  return (
    <svg viewBox="0 0 120 120" className={className} aria-hidden="true">
      <defs>
        <path id="taq-seal-top" d="M 22,60 A 38,38 0 0 1 98,60" fill="none" />
        <path id="taq-seal-bot" d="M 22,60 A 38,38 0 0 0 98,60" fill="none" />
      </defs>
      <circle cx="60" cy="60" r="56" fill="none" stroke="#b03030" strokeWidth="3.2" />
      <circle cx="60" cy="60" r="32" fill="none" stroke="#b03030" strokeWidth="2.5" />
      <text
        fill="#b03030"
        fontFamily="Times New Roman, Times, serif"
        fontWeight="700"
        fontSize="10"
        letterSpacing="1.1"
      >
        <textPath href="#taq-seal-top" startOffset="50%" textAnchor="middle">
          TheAIQualisys
        </textPath>
      </text>
      <text
        fill="#b03030"
        fontFamily="Times New Roman, Times, serif"
        fontWeight="700"
        fontSize="8"
        letterSpacing="0.6"
      >
        <textPath href="#taq-seal-bot" startOffset="50%" textAnchor="middle">
          Bangalore-560090
        </textPath>
      </text>
      {label ? (
        <text
          x="60"
          y="64"
          textAnchor="middle"
          fill="#b03030"
          fontFamily="Times New Roman, Times, serif"
          fontStyle="italic"
          fontWeight="700"
          fontSize={label.length > 12 ? 9 : 12}
        >
          {label}
        </text>
      ) : null}
    </svg>
  );
}
