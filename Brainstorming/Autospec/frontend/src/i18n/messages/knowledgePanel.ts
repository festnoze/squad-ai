import type { Namespace } from "./index";

export const knowledgePanel: Namespace = {
  title: { en: "Software memory", fr: "Mémoire logicielle" },
  tabAdrs: { en: "ADRs", fr: "ADRs" },
  tabDebt: { en: "Debt", fr: "Dette" },
  tabRisks: { en: "Risks", fr: "Risques" },
  tabIdeas: { en: "Pending ideas", fr: "Idées en suspens" },
  tabNotes: { en: "Notes & memory", fr: "Notes & mémoire" },
  emptyTab: { en: "No entries.", fr: "Aucune entrée." },
  architectureNotes: { en: "Architecture notes", fr: "Notes d'architecture" },
  componentMemory: { en: "Component memory — {stream}", fr: "Mémoire composant — {stream}" },
  sourceObservation: { en: "Source observation:", fr: "Observation source :" },
  editEntry: { en: "Edit this entry", fr: "Modifier cette entrée" },
  deleteEntry: { en: "Delete this entry", fr: "Supprimer cette entrée" },
  confirmDelete: {
    en: "Delete this entry? It will no longer be injected into prompts.",
    fr: "Supprimer cette entrée ? Elle ne sera plus injectée dans les prompts.",
  },
  decision: { en: "Decision", fr: "Décision" },
  context: { en: "Context", fr: "Contexte" },
  effort: { en: "Effort", fr: "Effort" },
  interest: { en: "Gets worse if", fr: "S'aggrave si" },
  likelihood: { en: "Likelihood", fr: "Probabilité" },
  mitigation: { en: "Mitigation", fr: "Mitigation" },
  valueHint: { en: "Value", fr: "Valeur" },
  reevaluateWhen: { en: "Re-evaluate when", fr: "Réévaluer quand" },
  iterationShort: { en: "iter. {n}", fr: "itér. {n}" },
};
