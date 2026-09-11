import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useTheme, type AppTheme } from "../theme/ThemeContext";

/** Existing Platform Admin desktop destinations — route paths must stay unchanged. */
const DESKTOP_APP_LINKS = [
  { to: "/admin/desktop-licensing", label: "Desktop licensing" },
  { to: "/admin/desktop-payments", label: "Desktop payments" },
  { to: "/admin/desktop-licenses", label: "Desktop licenses" },
  { to: "/admin/desktop-installers", label: "Desktop installers" },
] as const;

function isDesktopAppsPath(pathname: string): boolean {
  return DESKTOP_APP_LINKS.some(({ to }) => pathname === to || pathname.startsWith(`${to}/`));
}

function triggerClass(theme: AppTheme, isActive: boolean): string {
  if (theme === "light") {
    return `inline-flex h-9 items-center gap-1 whitespace-nowrap rounded-md px-3.5 text-sm font-medium leading-none ${
      isActive ? "bg-slate-800 text-white" : "text-slate-600 hover:bg-slate-200 hover:text-slate-900"
    }`;
  }
  if (theme === "grey") {
    return `inline-flex h-9 items-center gap-1 whitespace-nowrap rounded-md px-3.5 text-sm font-medium leading-none ${
      isActive ? "bg-zinc-700 text-white" : "text-zinc-600 hover:bg-zinc-300/80 hover:text-zinc-900"
    }`;
  }
  return `inline-flex h-9 items-center gap-1 whitespace-nowrap rounded-md px-3.5 text-sm font-medium leading-none ${
    isActive ? "bg-slate-800 text-white" : "text-slate-300 hover:bg-slate-800/80 hover:text-white"
  }`;
}

function menuPanelClass(theme: AppTheme): string {
  if (theme === "light") {
    return "min-w-[13.5rem] rounded-lg border border-slate-200 bg-white py-1 shadow-md";
  }
  if (theme === "grey") {
    return "min-w-[13.5rem] rounded-lg border border-zinc-300 bg-zinc-50 py-1 shadow-md";
  }
  return "min-w-[13.5rem] rounded-lg border border-slate-700 bg-slate-900 py-1 shadow-lg";
}

function menuItemClass(theme: AppTheme, isActive: boolean): string {
  if (theme === "light") {
    return `flex w-full items-center px-3.5 py-2 text-left text-sm font-medium ${
      isActive ? "bg-slate-800 text-white" : "text-slate-700 hover:bg-slate-100 hover:text-slate-900"
    }`;
  }
  if (theme === "grey") {
    return `flex w-full items-center px-3.5 py-2 text-left text-sm font-medium ${
      isActive ? "bg-zinc-700 text-white" : "text-zinc-700 hover:bg-zinc-200/80 hover:text-zinc-900"
    }`;
  }
  return `flex w-full items-center px-3.5 py-2 text-left text-sm font-medium ${
    isActive ? "bg-slate-800 text-white" : "text-slate-300 hover:bg-slate-800/80 hover:text-white"
  }`;
}

/**
 * Consolidates the four Desktop admin top-nav links into one disclosure menu.
 * Routes and AdminRoute guards are unchanged — this is presentation only.
 *
 * Menu uses position:fixed so it is not clipped by the header nav's overflow-x-auto.
 */
export default function AdminDesktopAppsNav() {
  const { theme } = useTheme();
  const loc = useLocation();
  const [open, setOpen] = useState(false);
  const [menuPos, setMenuPos] = useState<{ top: number; right: number }>({ top: 0, right: 0 });
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuId = useId();
  const sectionActive = isDesktopAppsPath(loc.pathname);

  function updateMenuPosition() {
    const el = triggerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    setMenuPos({
      top: rect.bottom,
      right: Math.max(8, window.innerWidth - rect.right),
    });
  }

  useEffect(() => {
    setOpen(false);
  }, [loc.pathname]);

  useLayoutEffect(() => {
    if (!open) return;
    updateMenuPosition();
    function onResize() {
      updateMenuPosition();
    }
    window.addEventListener("resize", onResize);
    window.addEventListener("scroll", onResize, true);
    return () => {
      window.removeEventListener("resize", onResize);
      window.removeEventListener("scroll", onResize, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;

    function onPointerDown(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div
      ref={rootRef}
      className="relative shrink-0"
      onMouseEnter={() => {
        updateMenuPosition();
        setOpen(true);
      }}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        ref={triggerRef}
        type="button"
        className={triggerClass(theme, sectionActive || open)}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-controls={menuId}
        onClick={() => {
          updateMenuPosition();
          setOpen((v) => !v);
        }}
      >
        Desktop Apps
        <span aria-hidden className="text-[0.65rem] leading-none opacity-80">
          ▾
        </span>
      </button>
      {open ? (
        <div
          className="z-50 pt-1"
          style={{ position: "fixed", top: menuPos.top, right: menuPos.right }}
        >
          <div id={menuId} role="menu" aria-label="Desktop Apps" className={menuPanelClass(theme)}>
            {DESKTOP_APP_LINKS.map(({ to, label }) => (
              <NavLink
                key={to}
                role="menuitem"
                to={to}
                className={({ isActive }) => menuItemClass(theme, isActive)}
                onClick={() => setOpen(false)}
              >
                {label}
              </NavLink>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
