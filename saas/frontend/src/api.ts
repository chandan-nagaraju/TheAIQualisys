const API_BASE = import.meta.env.VITE_API_URL ?? "";

export type TokenKind = "company" | "admin";

/** Human-readable message from FastAPI `detail` (string, object with `message`, or validation list). */
export function formatApiErrorDetail(detail: unknown): string {
  if (detail == null) return "Request failed";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((x) =>
        typeof x === "object" && x !== null && "msg" in x
          ? String((x as { msg: string }).msg)
          : JSON.stringify(x),
      )
      .join("; ");
  }
  if (typeof detail === "object" && detail !== null && "message" in detail) {
    const m = (detail as { message: unknown }).message;
    if (typeof m === "string") return m;
  }
  return JSON.stringify(detail);
}

function authHeader(kind: TokenKind): HeadersInit {
  const key = kind === "admin" ? "fir_admin_token" : "fir_token";
  const t = localStorage.getItem(key);
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export function apiUrl(path: string): string {
  const base = API_BASE.trim().replace(/\/+$/, "");
  if (!base) return path;
  // If deploy config uses VITE_API_URL ending with /api and caller already passes /api/*,
  // avoid generating /api/api/* which causes 404 in hosted setups.
  if (base.endsWith("/api") && path.startsWith("/api/")) {
    return `${base}${path.slice(4)}`;
  }
  return `${base}${path}`;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isFetchFailedError(err: unknown): boolean {
  return err instanceof TypeError && String((err as Error).message).toLowerCase().includes("fetch");
}

function asNetworkError(path: string, err: unknown): Error {
  if (isFetchFailedError(err)) {
    const url = apiUrl(path);
    const origin = typeof window !== "undefined" ? window.location.origin : "your Vercel origin";
    return new Error(
      `Cannot reach the API (${url}). This is often a temporary network glitch (try again), CORS if the browser console shows a CORS error (ensure Railway CORS_ORIGINS or PUBLIC_APP_URL includes ${origin} — we also add the apex/www pair when possible), a wrong VITE_API_URL in the frontend build, or the API being unreachable. For large ZIP jobs, keep this tab in the foreground until the download starts.`,
    );
  }
  return err instanceof Error ? err : new Error(String(err));
}

export async function apiFetch<T>(
  path: string,
  opts: RequestInit & { token?: TokenKind } = {},
): Promise<T> {
  const tokenKind = opts.token ?? "company";
  const { token: _t, ...rest } = opts;
  let res: Response;
  try {
    res = await fetch(apiUrl(path), {
      ...rest,
      headers: {
        "Content-Type": "application/json",
        ...authHeader(tokenKind),
        ...(rest.headers || {}),
      },
    });
  } catch (e) {
    throw asNetworkError(path, e);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      if (j?.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

/** GET JSON without Content-Type (some stacks reject GET + application/json). */
export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(apiUrl(path));
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      if (j?.detail != null) detail = formatApiErrorDetail(j.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export async function apiUpload(path: string, file: File, tokenKind: TokenKind = "company") {
  const key = tokenKind === "admin" ? "fir_admin_token" : "fir_token";
  const t = localStorage.getItem(key);
  const fd = new FormData();
  fd.append("file", file);
  let res: Response;
  try {
    res = await fetch(apiUrl(path), {
      method: "POST",
      headers: t ? { Authorization: `Bearer ${t}` } : {},
      body: fd,
    });
  } catch (e) {
    throw asNetworkError(path, e);
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

export async function apiDownloadBlob(path: string): Promise<Blob> {
  const t = localStorage.getItem("fir_token");
  let res: Response;
  try {
    res = await fetch(apiUrl(path), {
      headers: t ? { Authorization: `Bearer ${t}` } : {},
    });
  } catch (e) {
    throw asNetworkError(path, e);
  }
  if (!res.ok) throw new Error(await res.text());
  return res.blob();
}

/** Legacy FIR workspace (/api/app) — sends JWT + optional selected customer */
const LS_WORKSPACE_CUSTOMER = "fir_workspace_customer_id";

export function getWorkspaceCustomerId(): number | null {
  const s = localStorage.getItem(LS_WORKSPACE_CUSTOMER);
  if (!s) return null;
  const n = parseInt(s, 10);
  return Number.isNaN(n) ? null : n;
}

export function setWorkspaceCustomerId(id: number | null) {
  if (id == null) localStorage.removeItem(LS_WORKSPACE_CUSTOMER);
  else localStorage.setItem(LS_WORKSPACE_CUSTOMER, String(id));
}

/** GET binary (e.g. part master JSON export) with workspace auth headers */
export async function workspaceDownloadBlob(path: string): Promise<Blob> {
  const t = localStorage.getItem("fir_token");
  const cid = getWorkspaceCustomerId();
  const headers: Record<string, string> = {};
  if (t) headers.Authorization = `Bearer ${t}`;
  if (cid != null) headers["X-Customer-Id"] = String(cid);
  let res: Response;
  try {
    res = await fetch(apiUrl(path), { headers });
  } catch (e) {
    throw asNetworkError(path, e);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      if (j?.detail != null) detail = formatApiErrorDetail(j.detail);
    } catch {
      detail = await res.text();
    }
    throw new Error(detail);
  }
  return res.blob();
}

/**
 * Build a same-origin workspace URL with `token` for GET requests (new tab / anchor).
 * Blob URLs from fetch cannot be navigated in another window reliably (blank tab).
 */
export function workspaceAuthenticatedUrl(path: string): string {
  const token = localStorage.getItem("fir_token") || "";
  const u = new URL(path, window.location.origin);
  if (token) u.searchParams.set("token", token);
  return u.pathname + u.search + u.hash;
}

/**
 * Open a workspace PDF in a new tab via direct navigation.
 * Uses same-origin in local dev (Vite proxy) and API origin in hosted split deployments.
 */
export function openWorkspacePdfInNewTab(path: string): void {
  const href = workspaceAuthenticatedUrl(path);
  const win = window.open(href, "_blank", "noopener,noreferrer");
  if (!win) {
    throw new Error(
      "Pop-up blocked. Allow pop-ups for this site to view the PDF, or use the Download button.",
    );
  }
}

/**
 * Download a workspace PDF via authenticated GET URL + token query.
 */
export function downloadWorkspacePdf(path: string, filename: string): void {
  const href = workspaceAuthenticatedUrl(path);
  const safeName = filename.toLowerCase().endsWith(".pdf") ? filename : `${filename}.pdf`;
  const a = document.createElement("a");
  a.href = href;
  a.download = safeName;
  a.rel = "noopener";
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

export async function workspaceFetch<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const t = localStorage.getItem("fir_token");
  const cid = getWorkspaceCustomerId();
  const base: Record<string, string> = {};
  if (t) base.Authorization = `Bearer ${t}`;
  if (cid != null) base["X-Customer-Id"] = String(cid);
  const isForm = opts.body instanceof FormData;
  if (!isForm) base["Content-Type"] = "application/json";

  /* Short backoff: extra round-trips here block the UI during “network checking” flows. */
  const maxAttempts = 4;
  const baseDelayMs = 200;

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    let res: Response;
    try {
      res = await fetch(apiUrl(path), {
        ...opts,
        headers: { ...base, ...(opts.headers as Record<string, string>) },
      });
    } catch (e) {
      if (attempt < maxAttempts - 1 && isFetchFailedError(e)) {
        await delay(baseDelayMs * (attempt + 1));
        continue;
      }
      throw asNetworkError(path, e);
    }

    if ([502, 503, 504].includes(res.status) && attempt < maxAttempts - 1) {
      try {
        await res.arrayBuffer();
      } catch {
        /* ignore */
      }
      await delay(baseDelayMs * (attempt + 1));
      continue;
    }

    if (!res.ok) {
      let detail = res.statusText;
      try {
        const j = await res.json();
        if (j?.detail != null) detail = formatApiErrorDetail(j.detail);
      } catch {
        /* ignore */
      }
      throw new Error(detail);
    }
    if (res.status === 204) return undefined as T;
    const ct = res.headers.get("content-type");
    if (ct && !ct.includes("application/json")) return (await res.text()) as T;
    return res.json() as Promise<T>;
  }

  throw new Error("Request failed after retries");
}

export async function workspaceUploadInvoice(file: File) {
  const fd = new FormData();
  fd.append("invoice_file", file);
  return workspaceFetch<{ rows: Record<string, unknown>[]; columns: string[]; filename: string }>(
    "/api/app/upload/invoice",
    { method: "POST", body: fd },
  );
}

/** Multipart POST (field name must match FastAPI `File` param, default `file`). */
export async function workspacePostFile<T>(path: string, file: File, fieldName = "file"): Promise<T> {
  const t = localStorage.getItem("fir_token");
  const cid = getWorkspaceCustomerId();
  const headers: Record<string, string> = {};
  if (t) headers.Authorization = `Bearer ${t}`;
  if (cid != null) headers["X-Customer-Id"] = String(cid);
  const fd = new FormData();
  fd.append(fieldName, file);
  let res: Response;
  try {
    res = await fetch(apiUrl(path), { method: "POST", headers, body: fd });
  } catch (e) {
    throw asNetworkError(path, e);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      if (j?.detail != null) detail = formatApiErrorDetail(j.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

/**
 * FIR preview URL:
 * - local dev: relative /api/... when VITE_API_URL empty (Vite proxy)
 * - hosted split (Amplify + Railway): absolute backend URL so iframe loads HTML from API
 */
export function firPreviewUrl(params: Record<string, string>): string {
  const token = localStorage.getItem("fir_token") || "";
  const q = new URLSearchParams(params);
  if (token) q.set("token", token);
  const path = `/api/app/fir-preview?${q.toString()}`;
  return apiUrl(path);
}
