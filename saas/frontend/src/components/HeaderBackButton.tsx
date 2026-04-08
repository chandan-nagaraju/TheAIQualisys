import { useNavigate } from "react-router-dom";
import { useTheme } from "../theme/ThemeContext";

/** Icon-only browser back (history) */
export default function HeaderBackButton() {
  const nav = useNavigate();
  const { theme } = useTheme();

  const btn =
    theme === "light"
      ? "inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-slate-300 bg-white text-slate-700 shadow-sm hover:bg-slate-50"
      : theme === "grey"
        ? "inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-zinc-400 bg-white text-zinc-800 shadow-sm hover:bg-zinc-100"
        : "inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-slate-600 bg-slate-900 text-slate-200 shadow-sm hover:bg-slate-800";

  return (
    <button
      type="button"
      className={btn}
      aria-label="Go back to previous page"
      title="Back"
      onClick={() => nav(-1)}
    >
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5" aria-hidden>
        <path
          fillRule="evenodd"
          d="M12.79 5.23a.75.75 0 01-.02 1.06L8.832 10l3.938 3.71a.75.75 0 11-1.04 1.08l-4.5-4.25a.75.75 0 010-1.08l4.5-4.25a.75.75 0 011.06.02z"
          clipRule="evenodd"
        />
      </svg>
    </button>
  );
}
