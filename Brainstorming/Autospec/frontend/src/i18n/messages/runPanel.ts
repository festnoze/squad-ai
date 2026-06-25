import type { Namespace } from "./index";

export const runPanel: Namespace = {
  // Header
  title: { en: "Execution", fr: "Exécution" },
  iteration: { en: "iteration {n}", fr: "itération {n}" },
  paused: { en: " ⏸ paused", fr: " ⏸ en pause" },
  autoSpecLoop: { en: " (auto-spec loop)", fr: " (boucle auto-spec)" },

  // Phase labels
  phaseIdle: { en: "Waiting", fr: "En attente" },
  phaseSpec: { en: "📋 Specification (PM)", fr: "📋 Spécification (PM)" },
  phaseAnalyze: { en: "🔍 Backlog exploration (Analyst)", fr: "🔍 Exploration backlog (Analyste)" },
  phaseArchitect: { en: "🏛️ Architecture (design)", fr: "🏛️ Architecture (design)" },
  phasePlan: { en: "🏃 Planning (PO)", fr: "🏃 Planification (PO)" },
  phaseBuild: { en: "💻 BDD/TDD development", fr: "💻 Développement BDD/TDD" },
  phaseDone: { en: "✅ Iteration complete", fr: "✅ Itération terminée" },
  phaseStopped: { en: "⏹ Stopped", fr: "⏹ Arrêté" },
  phaseError: { en: "💥 Error", fr: "💥 Erreur" },

  // Error / banners
  errorTitle: { en: "Pipeline error detail", fr: "Détail de l'erreur de la pipeline" },
  errorNoDetail: {
    en: "Error without detail (see logs / chat).",
    fr: "Erreur sans détail (voir les logs / le chat).",
  },
  regressionTitle: {
    en: "Previously green tests were broken",
    fr: "Des tests précédemment verts ont été cassés",
  },
  regressionCount: { en: "⚠️ {n} regression(s)", fr: "⚠️ {n} régression(s)" },

  approvalTitle: { en: "Validation required before build", fr: "Validation requise avant le build" },
  approvalRequired: { en: "⏸ Validation required ({phase})", fr: "⏸ Validation requise ({phase})" },
  approve: { en: "✅ Approve", fr: "✅ Approuver" },
  reject: { en: "✋ Reject", fr: "✋ Rejeter" },

  resumeTitle: {
    en: "Claude usage window exhausted: work will resume automatically",
    fr: "Fenêtre d'usage Claude épuisée : le travail reprendra automatiquement",
  },
  resumeAt: { en: "⏰ Auto-resume at ", fr: "⏰ Reprise auto à " },
  cancelAutoResume: { en: "Cancel automatic resume", fr: "Annuler la reprise automatique" },

  // Usage / forecast meters
  usageTokens: { en: "tokens", fr: "tokens" },
  usageCalls: { en: "calls", fr: "appels" },
  forecastTitle: {
    en: "Estimated remaining cost (project cost/story history)",
    fr: "Estimation du coût restant (historique coût/story du projet)",
  },
  forecast: { en: "📈 ~${cost} / {n} story(ies)", fr: "📈 ~${cost} / {n} story(ies)" },

  // Run controls
  argsPlaceholder: { en: "arguments (e.g. auth-screen)…", fr: "arguments (ex. auth-screen)…" },
  argsTitle: {
    en: "CLI arguments passed to the generated application (optional)",
    fr: "Arguments CLI passés à l'application générée (optionnel)",
  },
  running: { en: "▶ Running…", fr: "▶ En cours…" },
  runProject: { en: "▶ Run project", fr: "▶ Lancer le projet" },
  resumeBuildTitle: {
    en: "Resume the build phase on the remaining stories",
    fr: "Reprendre la phase build sur les stories restantes",
  },
  resumeBuild: { en: "▶ Continue build", fr: "▶ Continuer le build" },
  retryFailedTitle: {
    en: "Reset and re-run all failed user stories",
    fr: "Réinitialiser et relancer toutes les user stories en échec",
  },
  retryFailed: { en: "🔄 Retry failures ({n})", fr: "🔄 Relancer les échecs ({n})" },
  stopAppTitle: { en: "Stop the generated application", fr: "Arrêter l'application générée" },
  stopApp: { en: "■ Stop app", fr: "■ Arrêter l'app" },
  resumePipelineTitle: { en: "Resume the pipeline", fr: "Reprendre la pipeline" },
  resumePipeline: { en: "▶ Resume", fr: "▶ Reprendre" },
  pausePipelineTitle: { en: "Pause the pipeline", fr: "Mettre la pipeline en pause" },
  pausePipeline: { en: "⏸ Pause", fr: "⏸ Pause" },
  stop: { en: "⏹ Stop", fr: "⏹ Stopper" },

  // Delivery menu
  deliveryTitle: {
    en: "Delivery & export of the generated product",
    fr: "Livraison & export du produit généré",
  },
  delivery: { en: "⋯ Delivery", fr: "⋯ Livraison" },
  doc: { en: "📘 Doc (README)", fr: "📘 Doc (README)" },
  exportZip: { en: "⬇ Export as zip", fr: "⬇ Exporter en zip" },
  gitCommit: { en: "🔀 Git commit", fr: "🔀 Commit git" },
  deploy: { en: "🚀 Deployment", fr: "🚀 Déploiement" },

  // Logs bar
  logsToggleTitle: { en: "Show / hide logs", fr: "Afficher / masquer les logs" },
  logsEmptyTitle: {
    en: "Logs will appear here during execution",
    fr: "Les logs apparaîtront ici pendant l'exécution",
  },
  logsCount: { en: "Logs ({n})", fr: "Logs ({n})" },
  logsEmpty: { en: "Logs — none yet", fr: "Logs — aucun pour l'instant" },
};
