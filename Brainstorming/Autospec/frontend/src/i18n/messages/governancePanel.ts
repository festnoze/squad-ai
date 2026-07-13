import type { Namespace } from "./index";

export const governancePanel: Namespace = {
  title: { en: "Backlog governance", fr: "Gouvernance du backlog" },
  pending: { en: "Awaiting approval", fr: "En attente d'approbation" },
  history: { en: "Decision log", fr: "Journal des décisions" },
  approve: { en: "Approve", fr: "Approuver" },
  reject: { en: "Reject", fr: "Rejeter" },
  confirmReject: { en: "Confirm rejection", fr: "Confirmer le rejet" },
  rejectReason: {
    en: "Rejection reason (optional)",
    fr: "Motif du rejet (optionnel)",
  },
  rationale: { en: "Rationale", fr: "Rationale" },
  sourceObservation: { en: "Source observation", fr: "Observation source" },
  // Decision statuses
  statusProposed: { en: "proposed", fr: "proposée" },
  statusApproved: { en: "approved", fr: "approuvée" },
  statusApplied: { en: "applied", fr: "appliquée" },
  statusRejectedByPolicy: { en: "rejected (policy)", fr: "rejetée (policy)" },
  statusRejectedByHuman: { en: "rejected (human)", fr: "rejetée (humain)" },
  statusInvalid: { en: "invalid", fr: "invalide" },
  // Human-readable backlog diff, one line per decision (action + payload).
  diffCreateTask: {
    en: "+ task “{title}” in {target}",
    fr: "+ tâche « {title} » dans {target}",
  },
  diffCreateStory: {
    en: "+ US “{title}” in {epic}",
    fr: "+ US « {title} » dans {epic}",
  },
  diffCreateTechStory: {
    en: "+ TS “{title}” in {epic}",
    fr: "+ TS « {title} » dans {epic}",
  },
  diffCreateEpic: {
    en: "+ epic “{title}”",
    fr: "+ EPIC « {title} »",
  },
  diffUpdateStory: {
    en: "{target} updated ({fields})",
    fr: "{target} modifiée ({fields})",
  },
  diffEnrichCriteria: {
    en: "{count} AC added to {target}",
    fr: "{count} AC ajouté(s) à {target}",
  },
  diffDefer: {
    en: "deferred as pending idea (“{title}”)",
    fr: "différé en idée en suspens (« {title} »)",
  },
  diffPersist: { en: "persisted to memory only", fr: "persisté en mémoire seulement" },
  diffDismiss: { en: "dismissed", fr: "ignorée" },
  fieldDescription: { en: "description", fr: "description" },
  fieldPriority: { en: "priority", fr: "priorité" },
  fieldTitle: { en: "title", fr: "titre" },
};
