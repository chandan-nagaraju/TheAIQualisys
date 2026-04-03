import type { NavigateFunction } from "react-router-dom";
import { setWorkspaceCustomerId } from "./api";

export function isTenantImpersonation(): boolean {
  return sessionStorage.getItem("fir_impersonating") === "1";
}

/** Restore platform admin session and leave tenant view. */
export function exitTenantImpersonation(nav: NavigateFunction): void {
  const backup = sessionStorage.getItem("fir_admin_token_backup");
  if (backup) localStorage.setItem("fir_admin_token", backup);
  sessionStorage.removeItem("fir_admin_token_backup");
  sessionStorage.removeItem("fir_impersonating");
  localStorage.removeItem("fir_token");
  setWorkspaceCustomerId(null);
  nav("/admin");
}
