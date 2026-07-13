import type { Namespace } from "./index";

export const observationsPanel: Namespace = {
  title: { en: "Engineering observations", fr: "Observations d'ingénierie" },
  empty: {
    en: "No observation matches the filters.",
    fr: "Aucune observation ne correspond aux filtres.",
  },
  // Filters
  filterType: { en: "Type", fr: "Type" },
  filterStatus: { en: "Status", fr: "Statut" },
  filterStream: { en: "Stream", fr: "Stream" },
  filterIteration: { en: "Iteration", fr: "Itération" },
  filterAll: { en: "All", fr: "Toutes" },
  // Observation types
  typeWorkaround: { en: "workaround", fr: "contournement" },
  typeTechDebt: { en: "tech debt", fr: "dette technique" },
  typeRisk: { en: "risk", fr: "risque" },
  typeLimitation: { en: "limitation", fr: "limitation" },
  typeRefactoring: { en: "refactoring", fr: "refactoring" },
  typeImprovement: { en: "improvement", fr: "amélioration" },
  typeAmbiguity: { en: "ambiguity", fr: "ambiguïté" },
  typeConstraint: { en: "constraint", fr: "contrainte" },
  typePattern: { en: "pattern", fr: "pattern" },
  // Statuses
  statusNew: { en: "new", fr: "nouvelle" },
  statusValidated: { en: "validated", fr: "validée" },
  statusRejected: { en: "rejected", fr: "rejetée" },
  statusRouted: { en: "routed", fr: "routée" },
  statusActioned: { en: "actioned", fr: "actionnée" },
  statusPersisted: { en: "persisted", fr: "persistée" },
  statusDeferred: { en: "deferred", fr: "différée" },
  statusDismissed: { en: "dismissed", fr: "ignorée" },
  // Urgencies
  urgencyLow: { en: "low", fr: "faible" },
  urgencyNormal: { en: "normal", fr: "normale" },
  urgencyHigh: { en: "high", fr: "haute" },
  urgencyCritical: { en: "critical", fr: "critique" },
  // Expanded detail
  description: { en: "Description", fr: "Description" },
  evidence: { en: "Evidence", fr: "Preuves" },
  impact: { en: "Impact", fr: "Impact" },
  workaround: { en: "Workaround applied", fr: "Contournement appliqué" },
  recommendations: { en: "Recommendations", fr: "Recommandations" },
  confidence: { en: "Confidence", fr: "Confiance" },
  reevaluateWhen: { en: "Re-evaluate when", fr: "Réévaluer quand" },
  routedTo: { en: "Routed to", fr: "Routée vers" },
  resolution: { en: "Resolution", fr: "Résolution" },
  linkedDecision: { en: "Linked PO decision", fr: "Décision PO liée" },
  source: { en: "Source", fr: "Source" },
  mergedCount: {
    en: "{count} duplicate(s) merged",
    fr: "{count} doublon(s) fusionné(s)",
  },
  iterationShort: { en: "iter. {n}", fr: "itér. {n}" },
  expand: { en: "Show details", fr: "Voir le détail" },
  collapse: { en: "Hide details", fr: "Masquer le détail" },
};
