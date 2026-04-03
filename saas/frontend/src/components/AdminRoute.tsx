import { Navigate, useLocation } from "react-router-dom";

/** Admin UI requires platform JWT from unified login (stored in fir_admin_token). */
export default function AdminRoute({ children }: { children: React.ReactNode }) {
  const loc = useLocation();
  const t = localStorage.getItem("fir_admin_token");
  if (!t) {
    return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  }
  return <>{children}</>;
}
