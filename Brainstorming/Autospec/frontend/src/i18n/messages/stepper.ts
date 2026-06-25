import type { Namespace } from "./index";

export const stepper: Namespace = {
  // Stage labels
  stageQueued: { en: "Queue", fr: "File" },
  stageAnalyzing: { en: "Analysis", fr: "Analyse" },
  stageContracts: { en: "Contracts", fr: "Contrats" },
  stageImplementing: { en: "Code", fr: "Code" },
  stageVerifying: { en: "Verify", fr: "Vérif" },
  stageMergeWait: { en: "Merge wait", fr: "Attente merge" },
  stageMerging: { en: "Merge", fr: "Merge" },
  stageDone: { en: "Done", fr: "Fini" },
  stageFailed: { en: "Failed", fr: "Échec" },
  // Auto-repair recovery labels
  recoveryRefining: { en: "refining", fr: "affinage" },
  recoveryCriticRestored: { en: "critic restored", fr: "critique restaurée" },
  recoveryRegressionRerun: { en: "regression rerun", fr: "rejeu régression" },
  recoveryMutationRerun: { en: "mutation rerun", fr: "rejeu mutation" },
  recoveryRetry: { en: "new attempt", fr: "nouvelle tentative" },
  stepsLabel: { en: "Stages {id}", fr: "Étapes {id}" },
};
