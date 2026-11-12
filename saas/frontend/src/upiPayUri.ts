/** NPCI UPI intent — scan or tap opens GPay, PhonePe, Paytm, CRED, etc. */

export function buildUpiPayUri(opts: {
  vpa: string;
  payeeName: string;
  amountInr: number;
  note: string;
}): string {
  const pa = (opts.vpa || "").trim();
  if (!pa) return "";
  const am = Number.isFinite(opts.amountInr) ? opts.amountInr : 0;
  const parts = [
    `pa=${encodeURIComponent(pa)}`,
    `pn=${encodeURIComponent((opts.payeeName || "TheAIQualisys").trim() || "TheAIQualisys")}`,
    `am=${encodeURIComponent(am.toFixed(2))}`,
    "cu=INR",
    `tn=${encodeURIComponent((opts.note || "TheAIQualisys").slice(0, 50))}`,
  ];
  return `upi://pay?${parts.join("&")}`;
}
