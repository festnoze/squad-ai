import type { Namespace } from "./index";

// Filled during the i18n migration of the matching component.
export const llmActivity: Namespace = {
  roleDev: { en: "Dev", fr: "Dev" },
  roleDevFrontend: { en: "Frontend dev", fr: "Dev front" },
  roleQa: { en: "QA", fr: "QA" },
  roleCritic: { en: "Critic", fr: "Critique" },
  roleJudge: { en: "Judge", fr: "Juge" },
  roleArchitect: { en: "Architect", fr: "Architecte" },
  roleAnalyst: { en: "Analyst", fr: "Analyste" },
  rolePm: { en: "PM", fr: "PM" },
  roleSm: { en: "PO/SM", fr: "PO/SM" },
  roleTechWriter: { en: "Writer", fr: "Rédacteur" },
  roleEvaluator: { en: "Evaluator", fr: "Évaluateur" },
  roleSecurityReviewer: { en: "Security", fr: "Sécurité" },
  roleRetro: { en: "Retro", fr: "Rétro" },
  timeAgoSeconds: { en: "{s}s ago", fr: "il y a {s}s" },
  timeAgoMinutes: { en: "{m} min ago", fr: "il y a {m} min" },
  timeAgoHours: { en: "{h} h ago", fr: "il y a {h} h" },
  badgeError: { en: "failed", fr: "échec" },
  errorHeading: { en: "Error", fr: "Erreur" },
  promptHeading: { en: "Prompt", fr: "Prompt" },
  responseHeading: { en: "Response", fr: "Réponse" },
  truncated: { en: " (truncated)", fr: " (tronqué)" },
  empty: { en: "(empty)", fr: "(vide)" },
  title: { en: "🧠 LLM calls", fr: "🧠 Appels LLM" },
  liveTitle: { en: "Live updates", fr: "Mise à jour en direct" },
  live: { en: "● live", fr: "● live" },
  emptyLive: {
    en: "No calls yet — they will appear here as soon as the agent works on this item.",
    fr: "Aucun appel pour l'instant — ils apparaîtront ici dès que l'agent travaille sur cet item.",
  },
  emptyHistory: {
    en: "No LLM call recorded for this item.",
    fr: "Aucun appel LLM enregistré pour cet item.",
  },
};
