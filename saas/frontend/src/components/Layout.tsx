import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";

import { setWorkspaceCustomerId } from "../api";



export default function Layout() {

  const loc = useLocation();

  const nav = useNavigate();

  const companyTok = localStorage.getItem("fir_token");

  const adminTok = localStorage.getItem("fir_admin_token");

  const isAdminRoute = loc.pathname.startsWith("/admin");



  function logoutCompany() {

    localStorage.removeItem("fir_token");

    setWorkspaceCustomerId(null);

    nav("/login");

  }



  function logoutAdmin() {

    localStorage.removeItem("fir_admin_token");

    nav("/login");

  }



  return (

    <div className="flex min-h-screen flex-col bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950">

      <header className="border-b border-slate-800/80 bg-slate-950/80 backdrop-blur">

        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-4">

          <Link

            to={isAdminRoute && adminTok ? "/admin" : companyTok ? "/dashboard" : "/"}

            className="text-lg font-semibold tracking-tight text-white"

          >

            TheAIQualisys

          </Link>

          <nav className="flex flex-wrap items-center gap-3 text-sm text-slate-300">

            {isAdminRoute && adminTok ? (

              <>

                <span className="text-xs uppercase tracking-wide text-amber-500/90">Platform admin</span>

                <Link className="hover:text-white" to="/admin">

                  All companies

                </Link>

                <Link className="hover:text-white" to="/admin/users">

                  Users &amp; customers

                </Link>

                <Link className="hover:text-white" to="/admin/pricing">

                  Pricing management

                </Link>

                <button

                  type="button"

                  className="rounded border border-slate-600 px-2 py-1 text-slate-200 hover:bg-slate-800"

                  onClick={logoutAdmin}

                >

                  Log out

                </button>

              </>

            ) : companyTok ? (

              <>

                <Link className="hover:text-white" to="/dashboard">

                  Dashboard

                </Link>

                <Link className="hover:text-white" to="/dashboard/billing">

                  Usage &amp; billing

                </Link>

                <button

                  type="button"

                  className="rounded border border-slate-600 px-2 py-1 text-slate-200 hover:bg-slate-800"

                  onClick={logoutCompany}

                >

                  Log out

                </button>

              </>

            ) : (

              <>

                <Link className="hover:text-white" to="/pricing">

                  About

                </Link>

                <Link className="hover:text-white" to="/pricing/all-modules">

                  Pricing

                </Link>

                <Link className="hover:text-white" to="/login">

                  Login

                </Link>

                <Link className="hover:text-white" to="/signup">

                  Sign up

                </Link>

              </>

            )}

          </nav>

        </div>

      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-10">

        <Outlet />

      </main>

      {!companyTok && !adminTok ? (

        <footer className="border-t border-slate-800/80 py-8 text-center text-xs text-slate-500">

          Developed by Chandan. Made with Cursor.ai.

        </footer>

      ) : null}

    </div>

  );

}

