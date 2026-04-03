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

export async function apiFetch<T>(
  path: string,
  opts: RequestInit & { token?: TokenKind } = {},
): Promise<T> {
  const tokenKind = opts.token ?? "company";
  const { token: _t, ...rest } = opts;
  const res = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...authHeader(tokenKind),
      ...(rest.headers || {}),
    },
  });
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

export async function apiUpload(path: string, file: File, tokenKind: TokenKind = "company") {
  const key = tokenKind === "admin" ? "fir_admin_token" : "fir_token";
  const t = localStorage.getItem(key);
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: t ? { Authorization: `Bearer ${t}` } : {},
    body: fd,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

export async function apiDownloadBlob(path: string): Promise<Blob> {
  const t = localStorage.getItem("fir_token");
  const res = await fetch(`${API_BASE}${path}`, {
    headers: t ? { Authorization: `Bearer ${t}` } : {},
  });
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
  const res = await fetch(`${API_BASE}${path}`, { headers });
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
 * Open a workspace PDF in a new tab via direct navigation (same origin as SPA, Vite proxies /api).
 * Synchronous on user click — avoids pop-up blocking and blob-URL cross-window issues.
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
 * Download a workspace PDF via authenticated GET (same-origin URL + token query).
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
  const res = await fetch(`${API_BASE}${path}`, {
    ...opts,
    headers: { ...base, ...(opts.headers as Record<string, string>) },
  });
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
  const res = await fetch(`${API_BASE}${path}`, { method: "POST", headers, body: fd });
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
 * FIR preview must load from the **same origin** as the SPA (e.g. /api/... on Vite dev
 * so the proxy hits FastAPI). If we prefix VITE_API_URL here, iframes and batch autofill
 * break with a cross-origin SecurityError. API JSON calls can still use API_BASE.
 */
export function firPreviewUrl(params: Record<string, string>): string {
  const token = localStorage.getItem("fir_token") || "";
  const q = new URLSearchParams(params);
  if (token) q.set("token", token);
  return `/api/app/fir-preview?${q.toString()}`;
}
