import type { Namespace } from "./index";

export const projectSetup: Namespace = {
  title: { en: "New project / feature", fr: "Nouveau projet / feature" },
  namePlaceholder: {
    en: "Project name (optional)",
    fr: "Nom du projet (optionnel)",
  },
  goalPlaceholder: {
    en: "Describe the feature or project you want to create…",
    fr: "Décris la feature ou le projet que tu veux créer…",
  },
  autoSpecLabel: { en: "Auto-spec", fr: "Auto-spec" },
  autoSpecDescription: {
    en: "— the PM decides everything on its own and chains iterations in a loop until manually stopped",
    fr: "— le PM décide de tout seul et enchaîne les itérations en boucle jusqu'à l'arrêt manuel",
  },
  briefPlaceholder: {
    en: "Spec to import (optional) — paste a set of requirements to skip the interview",
    fr: "Spec à importer (optionnel) — colle un cahier des charges pour court-circuiter l'interview",
  },
  brownfieldAriaLabel: {
    en: "Path to an existing repo to extend (brownfield mode, optional)",
    fr: "Chemin d'un repo existant à étendre (mode brownfield, optionnel)",
  },
  brownfieldPlaceholder: {
    en: "Existing repo to extend (path, optional — brownfield mode)",
    fr: "Repo existant à étendre (chemin, optionnel — mode brownfield)",
  },
  budgetAriaLabel: {
    en: "Maximum budget in dollars (empty = no limit)",
    fr: "Budget maximum en dollars (vide = pas de limite)",
  },
  budgetPlaceholder: {
    en: "Max budget ($) — empty = no limit",
    fr: "Budget max ($) — vide = pas de limite",
  },
  submitAutoSpec: {
    en: "🔁 Start the auto-spec loop",
    fr: "🔁 Lancer la boucle auto-spec",
  },
  submitSpec: {
    en: "🚀 Start the specification",
    fr: "🚀 Démarrer la spécification",
  },
};
