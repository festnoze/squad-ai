import type { Namespace } from "./index";

export const projectBar: Namespace = {
  selectActiveProject: {
    en: "Select the active project",
    fr: "Sélectionner le projet actif",
  },
  chooseProject: {
    en: "— Choose a project ({count}) —",
    fr: "— Choisir un projet ({count}) —",
  },
  phasePaused: { en: "{phase} (paused)", fr: "{phase} (pause)" },
  phasePausedDot: { en: "{phase} (paused)", fr: "{phase} (en pause)" },
  archived: { en: "archived", fr: "archivé" },
  progressTitle: {
    en: "{done} story(ies) completed out of {total}",
    fr: "{done} story(ies) terminée(s) sur {total}",
  },
  stopPipeline: {
    en: "Stop this project's pipeline",
    fr: "Stopper la pipeline de ce projet",
  },
  resumePipeline: { en: "Resume the pipeline", fr: "Reprendre la pipeline" },
  resumeBuild: {
    en: "Resume building the remaining stories",
    fr: "Reprendre le build des stories restantes",
  },
  unarchiveProject: { en: "Unarchive the project", fr: "Désarchiver le projet" },
  archiveProject: { en: "Archive the project", fr: "Archiver le projet" },
  deleteProject: { en: "Delete the project", fr: "Supprimer le projet" },
  inactiveHint: {
    en: "Inactive projects — available via the 🗂 selector",
    fr: "Projets inactifs — accessibles via le sélecteur 🗂",
  },
  hiddenCount: { en: "+{count} in 🗂", fr: "+{count} dans 🗂" },
  new: { en: "＋ New", fr: "＋ Nouveau" },
  hideArchived: {
    en: "Hide archived projects",
    fr: "Masquer les projets archivés",
  },
  showArchived: {
    en: "Show archived projects",
    fr: "Afficher les projets archivés",
  },
  archivedToggle: {
    en: "📦 Archived ({count})",
    fr: "📦 Archivés ({count})",
  },
};
