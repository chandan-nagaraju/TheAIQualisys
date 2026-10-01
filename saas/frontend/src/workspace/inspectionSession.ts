/** Persist inspection workflow state across browser refresh (React Router location.state is ephemeral). */

const KEY_EXTRACTED = "fir_ws_inspection_extracted_v1";
const KEY_SELECTION = "fir_ws_inspection_select_v1";
const KEY_RESULTS = "fir_ws_inspection_results_v1";

export type InspectionExtractedState = {
  rows: Record<string, unknown>[];
  columns: string[];
  filename?: string;
};

export type InspectionSelectionState = InspectionExtractedState;

export type InspectionResultsState = {
  rows: Record<string, unknown>[];
  filename?: string;
};

function readJson<T>(key: string): T | null {
  if (typeof sessionStorage === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

function writeJson(key: string, value: unknown): void {
  if (typeof sessionStorage === "undefined") return;
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* quota or private mode */
  }
}

function hasRows(state: { rows?: unknown[] } | null | undefined): boolean {
  return Boolean(state?.rows && Array.isArray(state.rows) && state.rows.length > 0);
}

export function loadInspectionExtracted(): InspectionExtractedState | null {
  const data = readJson<InspectionExtractedState>(KEY_EXTRACTED);
  return hasRows(data) ? data : null;
}

export function saveInspectionExtracted(state: InspectionExtractedState): void {
  writeJson(KEY_EXTRACTED, state);
}

export function loadInspectionSelection(): InspectionSelectionState | null {
  const data = readJson<InspectionSelectionState>(KEY_SELECTION);
  return hasRows(data) ? data : null;
}

export function saveInspectionSelection(state: InspectionSelectionState): void {
  writeJson(KEY_SELECTION, state);
}

export function loadInspectionResults(): InspectionResultsState | null {
  const data = readJson<InspectionResultsState>(KEY_RESULTS);
  return hasRows(data) ? data : null;
}

export function saveInspectionResults(state: InspectionResultsState): void {
  writeJson(KEY_RESULTS, state);
}

export function clearInspectionSession(): void {
  if (typeof sessionStorage === "undefined") return;
  sessionStorage.removeItem(KEY_EXTRACTED);
  sessionStorage.removeItem(KEY_SELECTION);
  sessionStorage.removeItem(KEY_RESULTS);
}

/**
 * Use React Router location.state when present; otherwise restore the last saved
 * payload for this step from sessionStorage (browser refresh).
 */
export function resolvePersistedRouteState<T extends { rows?: unknown[] }>(
  locState: T | null | undefined,
  load: () => T | null,
): T | null {
  if (hasRows(locState)) return locState as T;
  return load();
}
