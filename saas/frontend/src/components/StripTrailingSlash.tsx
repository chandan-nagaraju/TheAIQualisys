import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";

/** S3/Amplify 301s extensionless paths to a trailing slash. Keep the SPA URL slash-free. */
export default function StripTrailingSlash() {
  const loc = useLocation();
  const nav = useNavigate();
  useEffect(() => {
    if (loc.pathname.length > 1 && loc.pathname.endsWith("/")) {
      nav(`${loc.pathname.replace(/\/+$/, "")}${loc.search}${loc.hash}`, { replace: true });
    }
  }, [loc.hash, loc.pathname, loc.search, nav]);
  return null;
}
