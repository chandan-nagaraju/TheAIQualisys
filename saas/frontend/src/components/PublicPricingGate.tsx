import { Navigate } from "react-router-dom";
import AboutPage from "../pages/AboutPage";

/**
 * Guests: About (this route historically was /pricing; module-wise prices live at /pricing/all-modules).
 * Logged-in company users: full module catalog.
 */
export default function PublicPricingGate() {
  if (localStorage.getItem("fir_token")) {
    return <Navigate to="/pricing/all-modules" replace />;
  }
  return <AboutPage />;
}
