import type { Namespace } from "./index";

export const componentsPanel: Namespace = {
  statusProposed: { en: "proposed", fr: "proposé" },
  statusApproved: { en: "approved", fr: "approuvé" },
  statusCreated: { en: "created", fr: "créé" },
  statusRejected: { en: "discarded", fr: "écarté" },
  title: { en: "🧱 Product components", fr: "🧱 Composants du produit" },
  optional: { en: "(optional)", fr: "(optionnel)" },
  reject: { en: "Discard this component", fr: "Écarter ce composant" },
  approve: { en: "Approve this component", fr: "Approuver ce composant" },
  setupTitle: {
    en: "Actually create the approved components (folders, manifests)",
    fr: "Créer réellement les composants approuvés (dossiers, manifests)",
  },
  setup: {
    en: "🧱 Create approved components",
    fr: "🧱 Créer les composants approuvés",
  },
};
