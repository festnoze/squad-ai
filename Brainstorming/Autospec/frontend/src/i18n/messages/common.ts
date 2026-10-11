import type { Namespace } from "./index";

// Shared, reusable terms. Use `common.*` for generic words rather than
// re-declaring them in component namespaces.
export const common: Namespace = {
  close: { en: "Close", fr: "Fermer" },
  cancel: { en: "Cancel", fr: "Annuler" },
  save: { en: "Save", fr: "Enregistrer" },
  delete: { en: "Delete", fr: "Supprimer" },
  confirm: { en: "Confirm", fr: "Confirmer" },
  yes: { en: "Yes", fr: "Oui" },
  no: { en: "No", fr: "Non" },
  ok: { en: "OK", fr: "OK" },
  edit: { en: "Edit", fr: "Modifier" },
  add: { en: "Add", fr: "Ajouter" },
  remove: { en: "Remove", fr: "Retirer" },
  loading: { en: "Loading…", fr: "Chargement…" },
  retry: { en: "Retry", fr: "Réessayer" },
  refresh: { en: "Refresh", fr: "Rafraîchir" },
  error: { en: "Error", fr: "Erreur" },
  success: { en: "Success", fr: "Succès" },
  copy: { en: "Copy", fr: "Copier" },
  copied: { en: "Copied to clipboard", fr: "Copié dans le presse-papiers" },
  copyFailed: { en: "Copy failed", fr: "Échec de la copie" },
  undo: { en: "Undo", fr: "Annuler" },
  estimatedCost: { en: "Estimated: ${cost}", fr: "Estimation : ${cost}" },
  costEstimateAbout: { en: "About cost estimates", fr: "À propos des coûts estimés" },
  costEstimateIncomplete: {
    en: "⚠ Incomplete estimate: {n} call(s) without usage data",
    fr: "⚠ Estimation incomplète : {n} appel(s) sans données d'usage",
  },
  costEstimateHint: {
    en: "These amounts are usage estimates, not invoices. Actual billing depends on your provider and account. Interrupted calls or missing pricing may be absent; $0 does not guarantee no charge.",
    fr: "Ces montants sont des estimations d'usage, pas des factures. La facturation dépend du fournisseur et du compte utilisé. Des appels interrompus ou des tarifs manquants peuvent ne pas être comptabilisés ; $0 ne garantit pas la gratuité.",
  },
  budgetEstimateHint: {
    en: "The estimated budget is an execution guardrail checked between calls, not a billing cap. Calls already running can exceed it. Empty or 0 disables this guardrail.",
    fr: "Le budget estimatif est un garde-fou d'exécution vérifié entre les appels, pas un plafond de facturation. Les appels déjà en cours peuvent le dépasser. Vide ou 0 désactive ce garde-fou.",
  },
};
