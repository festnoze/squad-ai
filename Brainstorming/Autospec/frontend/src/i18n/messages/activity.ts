import type { Namespace } from "./index";

// Filled during the i18n migration of the matching component.
export const activity: Namespace = {
  personaDev: { en: "Dev", fr: "Dev" },
  personaQa: { en: "QA", fr: "QA" },
  personaCritic: { en: "Critic", fr: "Critique" },
  personaJudge: { en: "Judge", fr: "Juge" },
  personaArchitect: { en: "Architect", fr: "Architecte" },
  personaAnalyst: { en: "Analyst", fr: "Analyste" },
  personaPm: { en: "PM", fr: "PM" },
  personaPo: { en: "PO", fr: "PO" },

  guidanceQueued: { en: "queued", fr: "en file" },
  guidanceApplied: { en: "applied", fr: "appliquée" },
  guidanceTooLate: { en: "too late", fr: "trop tard" },

  stallMergeLock: {
    en: "Merge in progress (lock held by {holder})",
    fr: "Merge en cours (verrou détenu par {holder})",
  },
  stallAwaitingApproval: {
    en: "Awaiting approval",
    fr: "En attente d'une validation",
  },
  stallBudgetPaused: {
    en: "Budget reached — paused",
    fr: "Budget atteint — en pause",
  },

  noGuidance: {
    en: "No targeted guidance for this item.",
    fr: "Aucune consigne ciblée pour cet item.",
  },
  guidancePlaceholder: { en: "Targeted guidance for {id}…", fr: "Consigne ciblée pour {id}…" },
  guidanceAriaLabel: { en: "Targeted guidance for {id}", fr: "Consigne ciblée pour {id}" },
  send: { en: "Send", fr: "Envoyer" },

  extendTitle: {
    en: "Add acceptance criteria before the build",
    fr: "Ajouter des critères d'acceptance avant le build",
  },
  extendButton: { en: "＋ Extend criteria", fr: "＋ Étendre les critères" },
  extendPlaceholder: { en: "One criterion per line…", fr: "Un critère par ligne…" },
  extendAriaLabel: { en: "New criteria for {id}", fr: "Nouveaux critères pour {id}" },

  detailsAriaLabel: { en: "Details {id}", fr: "Détails {id}" },
  personaTitle: { en: "Current agent: {label}", fr: "Agent en cours : {label}" },
  actionsAriaLabel: { en: "Actions {id}", fr: "Actions {id}" },
  menuRetry: { en: "🔄 Restart", fr: "🔄 Relancer" },
  menuForceDone: { en: "✓ Force done", fr: "✓ Forcer terminé" },
  menuDiff: { en: "📊 Diff", fr: "📊 Diff" },
  menuChat: { en: "💬 Chat", fr: "💬 Chat" },
  blockedBy: { en: "⛔ blocked by {blockers}", fr: "⛔ bloqué par {blockers}" },
  diffTitle: { en: "📊 Diff — {id}", fr: "📊 Diff — {id}" },
  noDiff: { en: "No diff available.", fr: "Aucun diff disponible." },

  heading: { en: "⚡ Activity", fr: "⚡ Activité" },
  regionAriaLabel: { en: "Activity", fr: "Activité" },
  countRunningTitle: { en: "Running", fr: "En cours" },
  countRunning: { en: "{n} running", fr: "{n} en cours" },
  countQueuedTitle: { en: "Queued", fr: "En file" },
  countQueued: { en: "{n} queued", fr: "{n} en file" },
  countDoneTitle: { en: "Done", fr: "Faits" },
  countDone: { en: "{n} done", fr: "{n} faits" },
  countFailedTitle: { en: "Failed", fr: "En échec" },
  countFailed: { en: "{n} failed", fr: "{n} échecs" },

  attentionTitle: {
    en: "Failed or blocked items needing attention",
    fr: "Items en échec ou bloqués nécessitant une intervention",
  },
  attentionChip: { en: "⚠ {n} to handle", fr: "⚠ {n} à traiter" },
  stallTitle: {
    en: "Why nothing is progressing right now",
    fr: "Pourquoi rien ne progresse actuellement",
  },
  stall: { en: "⏸ {reason}", fr: "⏸ {reason}" },

  approvalRequired: { en: "⏸ Approval required —", fr: "⏸ Validation requise —" },
  approve: { en: "✅ Approve", fr: "✅ Approuver" },
  reject: { en: "✋ Reject", fr: "✋ Rejeter" },

  crewToggle: { en: "Crew", fr: "Équipe" },
  crewFilterAriaLabel: { en: "Filter by agent", fr: "Filtre par agent" },
  crewAll: { en: "All", fr: "Tous" },

  attentionRegionAriaLabel: { en: "To handle first", fr: "À traiter en priorité" },
  attentionRegionTitle: { en: "To handle", fr: "À traiter" },
  empty: {
    en: "No item to display. Activity will appear here during the build.",
    fr: "Aucun item à afficher. L'activité apparaîtra ici pendant le build.",
  },
};
