/** Routes where Layout shows full-width strips below the header (admin impersonation, trial countdown). */
export function showCompanyShellBannerPath(pathname: string): boolean {
  if (pathname === "/dashboard" || pathname === "/upgrade") return true;
  if (pathname.startsWith("/dashboard/")) return true;
  if (pathname.startsWith("/modules/")) return true;
  return false;
}
