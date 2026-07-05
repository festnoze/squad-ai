import type { Namespace } from "./index";

export const depGraph: Namespace = {
  title: { en: "Dependency graph", fr: "Graphe de dépendances" },
  summary: {
    en: "{n} items · {waves} waves · up to {parallel} in parallel · critical path {critical}",
    fr: "{n} éléments · {waves} vagues · jusqu'à {parallel} en parallèle · chemin critique {critical}",
  },
  backToProject: { en: "Project view", fr: "Vue projet" },
  expandAll: { en: "Expand all", fr: "Tout déplier" },
  collapseAll: { en: "Collapse all", fr: "Tout replier" },
  expand: { en: "Expand", fr: "Déplier" },
  collapse: { en: "Collapse", fr: "Replier" },
  focus: { en: "Focus on this item", fr: "Focus sur cet élément" },
  hint: {
    en: "Click: select · double-click: open in product vision · drag nodes to rearrange",
    fr: "Clic : sélection · double-clic : ouvrir dans la vision produit · glisser pour réorganiser",
  },
};
