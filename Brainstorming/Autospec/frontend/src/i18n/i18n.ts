import { useEffect, useReducer } from "react";
import { messages } from "./messages";

/** Supported UI languages. */
export type Lang = "en" | "fr";

export const LANGS: { value: Lang; label: string; flag: string }[] = [
  { value: "en", label: "English", flag: "🇬🇧" },
  { value: "fr", label: "Français", flag: "🇫🇷" },
];

const STORAGE_KEY = "autospec.lang";
const DEFAULT_LANG: Lang = "en";

function loadInitialLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "en" || saved === "fr") return saved;
  } catch {
    /* localStorage unavailable (SSR / privacy mode) — fall back to default */
  }
  return DEFAULT_LANG;
}

// Module-level locale store. Kept outside React so `t()` works anywhere
// (including non-component code) and a single source of truth drives every
// subscribed component to re-render on change.
let currentLang: Lang = loadInitialLang();
const listeners = new Set<() => void>();

export function getLang(): Lang {
  return currentLang;
}

export function setLang(lang: Lang): void {
  if (lang === currentLang) return;
  currentLang = lang;
  try {
    localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    /* ignore persistence failures */
  }
  document.documentElement.setAttribute("lang", lang);
  for (const fn of listeners) fn();
}

export function subscribeLang(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** Apply the persisted language to <html lang> at boot. */
export function initLang(): void {
  document.documentElement.setAttribute("lang", currentLang);
}

/**
 * Translate `key` for the current language. Falls back gracefully:
 * current lang → English → the key itself (so a missing entry is visible but
 * never crashes the UI). `vars` interpolates `{name}` placeholders.
 */
export function t(key: string, vars?: Record<string, string | number>): string {
  const entry = messages[key];
  let str = entry ? entry[currentLang] ?? entry.en : key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      str = str.replace(new RegExp(`\\{${k}\\}`, "g"), String(v));
    }
  }
  return str;
}

/**
 * React hook: returns a stable-enough `t` plus the current language and a
 * setter, and re-renders the calling component whenever the language changes.
 */
export function useI18n(): {
  t: typeof t;
  lang: Lang;
  setLang: typeof setLang;
} {
  const [, force] = useReducer((c: number) => c + 1, 0);
  useEffect(() => subscribeLang(force), []);
  return { t, lang: currentLang, setLang };
}
