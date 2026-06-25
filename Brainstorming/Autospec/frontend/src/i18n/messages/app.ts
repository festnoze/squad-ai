import type { Namespace } from "./index";

export const app: Namespace = {
  subtitle: {
    en: "PM → PO → QA → Dev, in BDD/TDD (BMAD method)",
    fr: "PM → PO → QA → Dev, en BDD/TDD (méthode BMAD)",
  },
  providerTitle: {
    en: "Agent provider & model (Claude / OpenAI / Ollama / Anthropic)",
    fr: "Provider & modèle d'agents (Claude / OpenAI / Ollama / Anthropic)",
  },
  providerDemo: { en: "demo", fr: "démo" },
  provider: { en: "Provider", fr: "Provider" },
  model: { en: "Model", fr: "Modèle" },
  modelLive: { en: "live", fr: "live" },
  modelSuggested: { en: "suggested", fr: "suggérés" },
  refreshModels: {
    en: "Refresh the actually-accessible models",
    fr: "Rafraîchir les modèles réellement accessibles",
  },
  refreshModelsAria: { en: "Refresh models", fr: "Rafraîchir les modèles" },
  dashboard: { en: "Factory dashboard", fr: "Dashboard de l'usine" },
  settings: { en: "Settings", fr: "Paramètres" },
  closeError: { en: "Close error message", fr: "Fermer le message d'erreur" },
  closeNotification: { en: "Close notification", fr: "Fermer la notification" },
  closeSetup: { en: "Close project creation", fr: "Fermer la création de projet" },
  placeholder: {
    en: "Select a project in the bar above, or create one with “＋ New”.",
    fr: "Sélectionne un projet dans la barre ci-dessus, ou crée-en un avec « ＋ Nouveau ».",
  },
  confirmDelete: {
    en: "Delete project “{name}” and all its generated code?",
    fr: "Supprimer le projet « {name} » et tout son code généré ?",
  },
  confirmRollback: {
    en: "Roll back to iteration {n}? The workspace will be restored to this snapshot.",
    fr: "Revenir à l'itération {n} ? Le workspace sera restauré à ce snapshot.",
  },
  rollbackToastTitle: { en: "Rollback", fr: "Rollback" },
  rollbackToastBody: { en: "Rolled back to iteration {n}.", fr: "Revenu à l'itération {n}." },
  deployToastTitle: { en: "Deployment", fr: "Déploiement" },
  deployToastArtifacts: {
    en: "Generated artifacts: {list}",
    fr: "Artefacts générés : {list}",
  },
  deployToastNone: {
    en: "Deployment artifacts already present.",
    fr: "Artefacts de déploiement déjà présents.",
  },
  commitToastTitle: { en: "Commit", fr: "Commit" },
  commitToastBody: { en: "Workspace committed: {commit}", fr: "Workspace commité : {commit}" },
};
