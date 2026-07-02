import type { Namespace } from "./index";

export const planReviewPanel: Namespace = {
  title: { en: "Plan review", fr: "Revue du plan" },
  score: { en: "Plan quality:", fr: "Qualité du plan :" },
  issues: { en: "Issues flagged", fr: "Problèmes signalés" },
  suggestions: { en: "Suggested improvements", fr: "Améliorations proposées" },
  clean: {
    en: "No issue flagged — the breakdown looks well sized.",
    fr: "Aucun problème signalé — le découpage paraît bien dimensionné.",
  },
  calibration: {
    en: "Downstream calibration (this iteration)",
    fr: "Calibration aval (cette itération)",
  },
  calib_reactive_splits: { en: "reactive split(s)", fr: "split(s) réactif(s)" },
  calib_over_budget_tasks: {
    en: "item(s) over the file budget",
    fr: "item(s) hors budget fichiers",
  },
  calib_degradations: { en: "pipeline degradation(s)", fr: "dégradation(s) du pipeline" },
  calib_merge_requeues: { en: "merge requeue(s)", fr: "requeue(s) de merge" },
  calib_p2b_resumes: {
    en: "green branch(es) resumed without rebuild",
    fr: "branche(s) verte(s) reprise(s) sans rebuild",
  },
  calib_orphan_resets: { en: "orphan reset(s)", fr: "reset(s) d'orphelin(s)" },
  calib_infra_retries: { en: "infra retry(ies)", fr: "retry(s) d'infra" },
};
