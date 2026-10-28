import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { apiFetch } from "../api";

type Note = {
  id: number;
  title: string;
  message: string;
  link_path: string;
  payment_id: number | null;
  is_read: boolean;
  created_at: string;
};

export default function AdminNotificationsNav() {
  const loc = useLocation();
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<Note[]>([]);

  useEffect(() => {
    if (!localStorage.getItem("fir_admin_token")) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await apiFetch<Note[]>("/admin/notifications", { token: "admin" });
        if (!cancelled) setRows(data);
      } catch {
        if (!cancelled) setRows([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loc.pathname]);

  const unread = rows.filter((r) => !r.is_read).length;

  async function markRead(id: number) {
    try {
      await apiFetch(`/admin/notifications/${id}/read`, { token: "admin", method: "POST", body: "{}" });
      setRows((prev) => prev.map((r) => (r.id === id ? { ...r, is_read: true } : r)));
    } catch {
      /* keep unread */
    }
  }

  return (
    <div className="relative shrink-0">
      <button
        type="button"
        className="inline-flex h-9 items-center whitespace-nowrap rounded-md px-3.5 text-sm font-medium text-slate-300 hover:bg-slate-800/80 hover:text-white"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        Alerts{unread > 0 ? ` (${unread})` : ""}
      </button>
      {open ? (
        <div className="absolute right-0 z-50 mt-1 w-[22rem] max-w-[90vw] rounded-lg border border-slate-700 bg-slate-900 py-1 shadow-lg">
          {rows.length === 0 && <p className="px-3.5 py-3 text-sm text-slate-500">No notifications.</p>}
          {rows.slice(0, 12).map((n) => (
            <Link
              key={n.id}
              to={n.link_path}
              className={`block px-3.5 py-2 text-left text-sm ${n.is_read ? "text-slate-400" : "text-slate-100"} hover:bg-slate-800`}
              onClick={() => {
                setOpen(false);
                if (!n.is_read) void markRead(n.id);
              }}
            >
              <p className="font-medium">{n.title}</p>
              <p className="mt-0.5 text-xs text-slate-500 line-clamp-2">{n.message}</p>
              <p className="mt-1 text-xs font-medium text-brand-500">View Payment</p>
            </Link>
          ))}
        </div>
      ) : null}
    </div>
  );
}
