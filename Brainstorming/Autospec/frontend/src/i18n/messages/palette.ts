import type { Namespace } from "./index";

// R2 — command palette (Cmd/Ctrl-K).
export const palette: Namespace = {
  title: { en: "Command palette", fr: "Palette de commandes" },
  inputAria: { en: "Command palette input", fr: "Saisie de la palette de commandes" },
  rootPlaceholder: {
    en: "Type a command…  (↑↓ to move, Enter to run, Esc to close)",
    fr: "Tape une commande…  (↑↓ pour naviguer, Entrée pour lancer, Échap pour fermer)",
  },
  targetPlaceholder: {
    en: "Pick a target (story or task)…",
    fr: "Choisis une cible (story ou tâche)…",
  },
  noResult: { en: "No match", fr: "Aucun résultat" },

  // Global commands
  goActivity: { en: "Go to Activity", fr: "Aller à Activité" },
  goVision: { en: "Go to Product Vision", fr: "Aller à Vision produit" },
  goGraph: { en: "Go to Graph", fr: "Aller au Graphe" },
  goIterations: { en: "Go to Iterations", fr: "Aller aux Itérations" },
  nextFailure: { en: "Go to next failure", fr: "Aller au prochain échec" },
  newProject: { en: "New project / feature", fr: "Nouveau projet / feature" },
  openDashboard: { en: "Open dashboard", fr: "Ouvrir le dashboard" },
  openSettings: { en: "Open settings", fr: "Ouvrir les paramètres" },

  // Target verbs
  goToItem: { en: "Go to item…", fr: "Aller à l'item…" },
  retryItem: { en: "Retry item…", fr: "Relancer l'item…" },
  forceItem: { en: "Force done item…", fr: "Forcer terminé l'item…" },

  // Hints (category shown on the right of a row)
  hintView: { en: "view", fr: "vue" },
  hintNav: { en: "navigate", fr: "naviguer" },
  hintAction: { en: "action", fr: "action" },
  hintApp: { en: "app", fr: "app" },

  confirmForceTitle: { en: "Force this item to done?", fr: "Forcer cet item à terminé ?" },
  confirmForceBody: {
    en: "Mark {id} as done without building it. Its acceptance criteria stay unchecked.",
    fr: "Marque {id} terminé sans le construire. Ses critères d'acceptance restent non couverts.",
  },
  actionFailed: { en: "Action failed", fr: "Action échouée" },
};
