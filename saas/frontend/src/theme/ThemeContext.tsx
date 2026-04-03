import { createContext, useContext, useEffect, useMemo, useState } from "react";

export type AppTheme = "dark" | "light" | "grey";

const LS_KEY = "fir_ui_theme";

function readStoredTheme(): AppTheme {
  try {
    const s = localStorage.getItem(LS_KEY);
    if (s === "light" || s === "grey" || s === "dark") return s;
  } catch {
    /* ignore */
  }
  return "dark";
}

type ThemeContextValue = {
  theme: AppTheme;
  setTheme: (t: AppTheme) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<AppTheme>(() =>
    typeof localStorage !== "undefined" ? readStoredTheme() : "dark",
  );

  useEffect(() => {
    try {
      localStorage.setItem(LS_KEY, theme);
    } catch {
      /* ignore */
    }
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  const setTheme = (t: AppTheme) => setThemeState(t);

  const value = useMemo(() => ({ theme, setTheme }), [theme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
