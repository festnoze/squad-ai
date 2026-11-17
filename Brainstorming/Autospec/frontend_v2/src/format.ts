// French labels and formatting shared by the screens.
import type { Phase, Profile, StoryStatus } from "./api";

export const PHASE_LABELS: Record<Phase, string> = {
  created: "Créé",
  brief: "Brief",
  plan: "Planification",
  build: "Construction",
  deliver: "Livraison",
  done: "Terminé",
  needs_attention: "À examiner",
  stopped: "Arrêté",
  error: "Erreur",
};

export const PROFILE_LABELS: Record<Profile, string> = {
  lib: "Bibliothèque (lib)",
  cli: "Ligne de commande (cli)",
  api: "API HTTP (api)",
  fullstack: "Fullstack (API + React)",
};

export const STATUS_LABELS: Record<StoryStatus, string> = {
  todo: "À faire",
  in_progress: "En cours",
  done: "Terminée",
  failed: "Échec",
};

const usd = new Intl.NumberFormat("fr-FR", {
  style: "currency",
  currency: "USD",
  currencyDisplay: "narrowSymbol",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatCost(value: number): string {
  return usd.format(Number.isFinite(value) ? value : 0);
}

const dateTime = new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" });
const timeOnly = new Intl.DateTimeFormat("fr-FR", { timeStyle: "medium" });

function parseDate(value: string | number | Date): Date | null {
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDateTime(value: string | number | Date): string {
  const date = parseDate(value);
  return date ? dateTime.format(date) : String(value);
}

export function formatTime(value: string | undefined): string {
  const date = value ? parseDate(value) : null;
  return date ? timeOnly.format(date) : "";
}

/** "dans 12 min" for an epoch-seconds instant, "imminente" once it is reached. */
export function formatCountdown(epochSeconds: number, nowMs: number = Date.now()): string {
  const minutes = Math.ceil((epochSeconds * 1000 - nowMs) / 60000);
  if (minutes <= 0) return "imminente";
  if (minutes < 60) return `dans ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `dans ${hours} h ${rest} min` : `dans ${hours} h`;
}
