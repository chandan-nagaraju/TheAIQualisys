/** Invoice / FIR report date normalization (matches backend fir_intelligence_ingest rules). */

const MIN_YEAR = 2000;
const MAX_YEAR = 2100;

export function normalizeInvoiceDateDisplay(raw: string | null | undefined): string | null {
  const s = String(raw ?? "").trim();
  if (!s) return null;

  if (/^\d{1,2}\s*[-/]\s*\d{1,2}$/.test(s)) return null;
  if (/\/\d{1,2}\s*[-–]\s*\d{1,2}\b/.test(s)) return null;

  const dmY = s.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/);
  if (dmY) {
    const y = Number(dmY[3]);
    if (y >= MIN_YEAR && y <= MAX_YEAR) {
      return `${dmY[1].padStart(2, "0")}.${dmY[2].padStart(2, "0")}.${dmY[3]}`;
    }
    return null;
  }

  const iso = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (iso) {
    const y = Number(iso[1]);
    if (y >= MIN_YEAR && y <= MAX_YEAR) {
      return `${iso[3]}.${iso[2]}.${iso[1]}`;
    }
    return null;
  }

  if (/^\d{1,5}$/.test(s)) return null;

  return null;
}

/** FIR header DATE: validated dd.mm.yyyy from row, else from server ISO fallback. */
export function reportDateForFIR(rowDate: string | null | undefined, fallbackIso: string): string {
  const norm = normalizeInvoiceDateDisplay(rowDate);
  if (norm) return norm;
  const fb = normalizeInvoiceDateDisplay(fallbackIso);
  if (fb) return fb;
  const m = fallbackIso.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (m) return `${m[3]}.${m[2]}.${m[1]}`;
  return fallbackIso;
}

export function isValidInvoiceDateInput(raw: string): boolean {
  return normalizeInvoiceDateDisplay(raw) !== null;
}
