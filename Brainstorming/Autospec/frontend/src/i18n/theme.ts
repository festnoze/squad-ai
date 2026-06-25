import { useEffect, useReducer } from "react";

/** Supported color themes. */
export type Theme = "dark" | "light";

const STORAGE_KEY = "autospec.theme";
const DEFAULT_THEME: Theme = "dark";

function loadInitialTheme(): Theme {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "dark" || saved === "light") return saved;
  } catch {
    /* localStorage unavailable — fall back to default */
  }
  return DEFAULT_THEME;
}

let currentTheme: Theme = loadInitialTheme();
const listeners = new Set<() => void>();

function apply(theme: Theme): void {
  // The CSS variable sets live under `:root[data-theme="dark|light"]`.
  document.documentElement.setAttribute("data-theme", theme);
}

export function getTheme(): Theme {
  return currentTheme;
}

export function setTheme(theme: Theme): void {
  if (theme === currentTheme) return;
  currentTheme = theme;
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    /* ignore persistence failures */
  }
  apply(theme);
  for (const fn of listeners) fn();
}

export function toggleTheme(): void {
  setTheme(currentTheme === "dark" ? "light" : "dark");
}

export function subscribeTheme(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** Apply the persisted theme to <html data-theme> at boot. */
export function initTheme(): void {
  apply(currentTheme);
}

/** React hook: current theme + setter, re-rendering on change. */
export function useTheme(): {
  theme: Theme;
  setTheme: typeof setTheme;
  toggleTheme: typeof toggleTheme;
} {
  const [, force] = useReducer((c: number) => c + 1, 0);
  useEffect(() => subscribeTheme(force), []);
  return { theme: currentTheme, setTheme, toggleTheme };
}
