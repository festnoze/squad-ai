import type { Namespace } from "./index";

export const board: Namespace = {
  // Status labels (STATUS_LABEL)
  status_todo: { en: "To do", fr: "À faire" },
  status_in_progress: { en: "In progress", fr: "Dev en cours" },
  status_red: { en: "Tests red", fr: "Tests rouges" },
  status_green: { en: "Tests green", fr: "Tests verts" },
  status_done: { en: "Done", fr: "Terminé" },
  status_failed: { en: "Failed", fr: "Échec" },

  // Test state labels (TEST_STATE_LABEL)
  testState_nonexistent: { en: "nonexistent", fr: "inexistant" },
  testState_red: { en: "red", fr: "rouge" },
  testState_green: { en: "green", fr: "vert" },

  // Stream kind labels (STREAM_META)
  stream_backend: { en: "Backend", fr: "Backend" },
  stream_frontend: { en: "Frontend", fr: "Frontend" },
  stream_cache: { en: "Cache", fr: "Cache" },
  stream_database: { en: "DB", fr: "BDD" },
  stream_other: { en: "Other", fr: "Autre" },

  // StreamBadge
  streamBadge_title: { en: "Stream « {id} » ({kind})", fr: "Stream « {id} » ({kind})" },

  // BlockedBadge
  blocked_title: {
    en: "Waiting on an unfinished dependency",
    fr: "En attente d'une dépendance non terminée",
  },
  blocked_label: { en: "blocked by {blockers}", fr: "bloquée par {blockers}" },

  // MergeBadge
  merge_ok_title: { en: "Code merged", fr: "Code mergé" },
  merge_ok_label: { en: "merged", fr: "mergé" },
  merge_conflict_title: {
    en: "Failed on inter-stream merge conflict",
    fr: "Échec sur conflit de merge inter-stream",
  },
  merge_conflict_label: { en: "merge conflict", fr: "conflit de merge" },

  // IterationBadge
  iteration_compact: { en: "it. {n}", fr: "it. {n}" },
  iteration_full: { en: "iteration {n}", fr: "itération {n}" },
  iteration_title: {
    en: "View iteration {n} in the timeline",
    fr: "Voir l'itération {n} dans la chronologie",
  },

  // CriterionRow
  acceptanceTests_heading: { en: "Acceptance tests ({count})", fr: "Tests d'acceptance ({count})" },
  noUnitTest: {
    en: "No unit test attached — covered by the Gherkin functional test below.",
    fr: "Aucun test unitaire rattaché — couvert par le test fonctionnel Gherkin ci-dessous.",
  },
  testMocks: { en: "mocks: {mocks}", fr: "mocks : {mocks}" },
  gherkinAssociated: { en: "Associated Gherkin", fr: "Gherkin associé" },

  // StoryEditor
  field_title: { en: "Title", fr: "Titre" },
  field_description: { en: "Description", fr: "Description" },
  field_priority: { en: "Priority (1=high)", fr: "Priorité (1=haute)" },
  field_criteria: { en: "Acceptance criteria", fr: "Critères d'acceptance" },
  field_gherkin: { en: "Gherkin", fr: "Gherkin" },
  criterion_placeholder: { en: "Criterion…", fr: "Critère…" },
  removeCriterion_title: { en: "Remove this criterion", fr: "Supprimer ce critère" },
  addCriterion: { en: "+ criterion", fr: "+ critère" },

  // DiffViewer
  diff_title: { en: "Diff — {label}", fr: "Diff — {label}" },
  diff_none: {
    en: "No diff available for this story.",
    fr: "Aucun diff disponible pour cette story.",
  },

  // StoryBadges
  prio_title: { en: "Kanban priority (1=high)", fr: "Priorité kanban (1=haute)" },
  statusBadge_title: { en: "View this item's LLM calls", fr: "Voir les appels LLM de cet item" },
  quality_title: { en: "Code quality (refinement)", fr: "Qualité du code (raffinement)" },
  mutation_title: { en: "Test robustness (mutation testing)", fr: "Robustesse des tests (mutation testing)" },
  coverage_title: { en: "Test coverage", fr: "Couverture de tests" },

  // StoryRow / common deps + tasks
  dragHandle_title: { en: "Drag to reorder", fr: "Glisser pour réordonner" },
  dragHandle_aria: { en: "Drag handle", fr: "Poignée de déplacement" },
  dependsOn: { en: "depends on {deps}", fr: "dépend de {deps}" },
  tasks_count: { en: "{count} task", fr: "{count} tâche" },
  tasks_count_plural: { en: "{count} tasks", fr: "{count} tâches" },
  storyOpenHint: { en: "details", fr: "détails" },

  // StoryDetail
  confirmDeleteStory: {
    en: "Delete user story « {title} »?",
    fr: "Supprimer la user story « {title} » ?",
  },
  action_edit: { en: "Edit", fr: "Éditer" },
  action_delete: { en: "Delete", fr: "Supprimer" },
  action_relaunch: { en: "Relaunch", fr: "Relancer" },
  relaunchStory_title: {
    en: "Reset and rebuild this user story",
    fr: "Réinitialiser et reconstruire cette user story",
  },
  action_forceDone: { en: "Force done", fr: "Forcer terminé" },
  forceDoneStory_title: {
    en: "Mark this user story as done without rebuilding it",
    fr: "Marquer cette user story comme terminée sans la reconstruire",
  },
  action_replay: { en: "Replay", fr: "Rejouer" },
  action_split: { en: "Split finer", fr: "Découper plus fin" },
  splitItem_title: {
    en: "Re-analyze this failed unit and split it into finer sub-tasks (too big for one agent session), then resume the build",
    fr: "Ré-analyser cette unité en échec et la découper en sous-tâches plus fines (trop grosse pour une session d'agent), puis reprendre le build",
  },
  action_diff: { en: "Diff", fr: "Diff" },
  acceptanceCriteria_heading: { en: "Acceptance criteria", fr: "Critères d'acceptance" },
  lastError_heading: { en: "Last error", fr: "Dernière erreur" },

  // TaskDetail
  taskStatusBadge_title: { en: "View this task's LLM calls", fr: "Voir les appels LLM de cette tâche" },
  relaunchTask_title: {
    en: "Reset and rebuild this task",
    fr: "Réinitialiser et reconstruire cette tâche",
  },
  forceDoneTask_title: {
    en: "Mark this task as done without rebuilding it",
    fr: "Marquer cette tâche comme terminée sans la reconstruire",
  },

  // AddStoryForm
  titleRequired: { en: "Title is required.", fr: "Le titre est requis." },
  addStory: { en: "+ Add a US", fr: "+ Ajouter une US" },
  field_titleRequired: { en: "Title *", fr: "Titre *" },
  create: { en: "Create", fr: "Créer" },

  // EpicStories
  reorderFailed: { en: "Reorder failed: {error}", fr: "Échec du réordonnancement : {error}" },

  // Breadcrumb
  breadcrumb_aria: { en: "Breadcrumb", fr: "Fil d'Ariane" },
  breadcrumb_epics: { en: "Epics", fr: "Épics" },

  // EpicProgressBar
  progress_title: {
    en: "{done}/{total} done — {pct}%",
    fr: "{done}/{total} terminée(s) — {pct}%",
  },
  progress_done: { en: "{done}/{total} done", fr: "{done}/{total} terminée(s)" },
  progress_inProgress: { en: "{count} in progress", fr: "{count} en cours" },
  progress_failed: { en: "{count} failed", fr: "{count} en échec" },

  // EpicCard / EpicView
  developmentInProgress: { en: "Development in progress", fr: "Développement en cours" },

  // Board top-level / empty states
  boardTitle: { en: "Board Epics / User stories", fr: "Board Epics / User stories" },
  empty_planning: {
    en: "The PM/PO is generating the plan… epics and user stories will appear here.",
    fr: "Le PM/PO génère le plan… les épics et user stories apparaîtront ici.",
  },
  empty_building: {
    en: "Build in progress… the plan will appear.",
    fr: "Construction en cours… le plan va s'afficher.",
  },
  empty_noPlan_before: {
    en: "No plan yet. Start the specification from the ",
    fr: "Pas encore de plan. Lance la spécification depuis le panneau ",
  },
  empty_noPlan_execution: { en: "Execution", fr: "Exécution" },
  empty_noPlan_after: {
    en: " panel below to generate epics & user stories.",
    fr: " ci-dessous pour générer épics & user stories.",
  },

  // Stream filter
  streamFilter_aria: { en: "Filter by stream", fr: "Filtre par stream" },
  streamFilter_all: { en: "All streams", fr: "Tous les streams" },

  // US view tasks heading
  tasksHeading: { en: "Tasks ({count})", fr: "Tâches ({count})" },
};
