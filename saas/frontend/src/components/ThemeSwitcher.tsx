import type { FC } from "react";
import { useTheme, type AppTheme } from "../theme/ThemeContext";

const OPTIONS: { id: AppTheme; label: string; title: string }[] = [
  { id: "dark", label: "Dark", title: "Dark mode (night)" },
  { id: "light", label: "Light", title: "Light mode (day)" },
  { id: "grey", label: "Grey", title: "Grey mode (evening)" },
];

function IconDark({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 20 20" fill="currentColor" aria-hidden>
      <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z" />
    </svg>
  );
}

function IconLight({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 20 20" fill="currentColor" aria-hidden>
      <path
        fillRule="evenodd"
        d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function IconGrey({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 20 20" fill="currentColor" aria-hidden>
      <path
        fillRule="evenodd"
        d="M10 18a8 8 0 100-16 8 8 0 000 16zm0-2a6 6 0 01-6-6h12a6 6 0 01-6 6z"
        clipRule="evenodd"
      />
    </svg>
  );
}

const ICONS: Record<AppTheme, FC<{ className?: string }>> = {
  dark: IconDark,
  light: IconLight,
  grey: IconGrey,
};

export default function ThemeSwitcher() {
  const { theme, setTheme } = useTheme();

  const wrap =
    theme === "light"
      ? "border-slate-300 bg-slate-100/80"
      : theme === "grey"
        ? "border-zinc-400/90 bg-zinc-200/90"
        : "border-slate-600/60 bg-slate-900/60";

  const active =
    theme === "light"
      ? "bg-white text-slate-900 shadow-sm"
      : theme === "grey"
        ? "bg-white text-zinc-900 shadow-sm"
        : "bg-slate-700 text-white shadow-sm";

  const idle =
    theme === "light"
      ? "text-slate-600 hover:text-slate-900 hover:bg-slate-200/80"
      : theme === "grey"
        ? "text-zinc-600 hover:text-zinc-900 hover:bg-zinc-300/80"
        : "text-slate-400 hover:text-white hover:bg-slate-800/80";

  return (
    <div className={`flex shrink-0 rounded-lg border p-0.5 ${wrap}`} role="group" aria-label="Color theme">
      {OPTIONS.map(({ id, label, title }) => {
        const Icon = ICONS[id];
        return (
          <button
            key={id}
            type="button"
            aria-pressed={theme === id}
            aria-label={label}
            title={title}
            className={`rounded-md p-1.5 transition-colors sm:p-2 ${theme === id ? active : idle}`}
            onClick={() => setTheme(id)}
          >
            <Icon className="h-4 w-4 sm:h-[1.125rem] sm:w-[1.125rem]" />
          </button>
        );
      })}
    </div>
  );
}
