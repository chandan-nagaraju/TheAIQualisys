import AdminHeaderNavMenu from "./AdminHeaderNavMenu";

/** Existing Platform Admin desktop destinations — route paths must stay unchanged. */
const DESKTOP_APP_LINKS = [
  { to: "/admin/desktop-licensing", label: "Desktop licensing" },
  { to: "/admin/desktop-payments", label: "Desktop payments" },
  { to: "/admin/desktop-licenses", label: "Desktop licenses" },
  { to: "/admin/desktop-installers", label: "Desktop installers" },
] as const;

/**
 * Consolidates the four Desktop admin top-nav links into one disclosure menu.
 * Routes and AdminRoute guards are unchanged — this is presentation only.
 */
export default function AdminDesktopAppsNav() {
  return <AdminHeaderNavMenu label="Desktop Apps" links={DESKTOP_APP_LINKS} />;
}
