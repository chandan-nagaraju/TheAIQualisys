/** FIR / Parts master: uppercase A–Z and digits 0–9 only (strip other characters). */
export function sanitizePartNoUpper(v: string): string {
  return v.replace(/[^A-Za-z0-9]/g, "").toUpperCase();
}

/** Part description: keep spaces and common punctuation; uppercase; collapse whitespace. */
export function sanitizePartMasterDescription(v: string): string {
  const kept = Array.from(v.toUpperCase())
    .filter((c) => /[A-Z0-9 \-./()&+]/.test(c))
    .join("");
  return kept.replace(/\s+/g, " ").trim();
}
