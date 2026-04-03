import { useTheme, type AppTheme } from "../theme/ThemeContext";

const OPTIONS: { id: AppTheme; label: string }[] = [
  { id: "dark", label: "Dark" },
  { id: "light", label: "Light" },
  { id: "grey", label: "Grey" },
];

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
    <div
      className={`flex shrink-0 rounded-lg border p-0.5 text-xs font-medium ${wrap}`}
      role="group"
      aria-label="Color theme"
    >
      {OPTIONS.map(({ id, label }) => (
        <button
          key={id}
          type="button"
          aria-pressed={theme === id}
          className={`rounded-md px-2 py-1 transition-colors sm:px-2.5 ${theme === id ? active : idle}`}
          onClick={() => setTheme(id)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
