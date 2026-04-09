/** FIR / Parts master: uppercase A–Z and digits 0–9 only (strip other characters). */
export function sanitizePartNoUpper(v: string): string {
  return v.replace(/[^A-Za-z0-9]/g, "").toUpperCase();
}
