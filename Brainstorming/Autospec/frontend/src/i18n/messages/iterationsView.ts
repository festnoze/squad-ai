import type { Namespace } from "./index";

export const iterationsView: Namespace = {
  // Story status labels
  statusTodo: { en: "To do", fr: "À faire" },
  statusInProgress: { en: "Dev in progress", fr: "Dev en cours" },
  statusRed: { en: "Tests red", fr: "Tests rouges" },
  statusGreen: { en: "Tests green", fr: "Tests verts" },
  statusDone: { en: "Done", fr: "Terminé" },
  statusFailed: { en: "Failed", fr: "Échec" },
  // Iteration state labels
  stateWorking: { en: "● in progress", fr: "● en cours" },
  stateDone: { en: "✓ delivered", fr: "✓ livrée" },
  stateFailed: { en: "⚠ failed", fr: "⚠ en échec" },
  statePending: { en: "to do", fr: "à faire" },
  title: { en: "🕒 Iterations", fr: "🕒 Itérations" },
  hint: {
    en: "Build timeline — click an item to open it in the product vision",
    fr: "Chronologie du build — clic sur un élément pour l'ouvrir dans la vision produit",
  },
  iteration: { en: "Iteration {n}", fr: "Itération {n}" },
  countsOne: { en: "{epics} epic · {done}/{total} US", fr: "{epics} épic · {done}/{total} US" },
  countsMany: { en: "{epics} epics · {done}/{total} US", fr: "{epics} épics · {done}/{total} US" },
  usageTitle: {
    en: "Cost and tokens consumed during this iteration",
    fr: "Coût et tokens consommés durant cette itération",
  },
  usageOne: { en: "{calls} agent call", fr: "{calls} appel agent" },
  usageMany: { en: "{calls} agent calls", fr: "{calls} appels agent" },
  openEpicTitle: {
    en: "Open epic {id} in the product vision",
    fr: "Ouvrir l'epic {id} dans la vision produit",
  },
  openStoryTitle: {
    en: "Open {id} in the product vision",
    fr: "Ouvrir {id} dans la vision produit",
  },
  noStories: {
    en: "No user story in this iteration.",
    fr: "Aucune user story dans cette itération.",
  },
  rollbackTitle: {
    en: "Restore the workspace to the iteration {n} snapshot",
    fr: "Restaurer le workspace au snapshot de l'itération {n}",
  },
  rollbackButton: {
    en: "↩ Go back to this iteration",
    fr: "↩ Revenir à cette itération",
  },
};
