import type { Namespace } from "./index";

export const dashboard: Namespace = {
  title: { en: "📊 Factory dashboard", fr: "📊 Dashboard de l'usine" },
  projects: { en: "Projects", fr: "Projets" },
  totalCost: { en: "Total cost", fr: "Coût total" },
  agentCalls: { en: "Agent calls", fr: "Appels agent" },
  stories: { en: "Stories", fr: "Stories" },
  done: { en: "Completed", fr: "Terminées" },
  failed: { en: "Failed", fr: "Échouées" },
  successRate: { en: "Success rate", fr: "Taux de succès" },
  avgAttempts: { en: "Avg. attempts", fr: "Tentatives moy." },
  costPerStory: { en: "Cost / story", fr: "Coût / story" },
  avgQuality: { en: "Avg. quality", fr: "Qualité moy." },
  avgMutation: { en: "Avg. mutation", fr: "Mutation moy." },
  avgCoverage: { en: "Avg. coverage", fr: "Couverture moy." },
  findings: { en: "Findings", fr: "Findings" },
  regressions: { en: "Regressions", fr: "Régressions" },
  // P3 (GENERATION_FUSION_REVIEW) - cost of the merge/canary loop.
  fusionTitle: { en: "Fusion loop", fr: "Boucle de fusion" },
  fusionSuitesPerItem: { en: "Suites / delivered item", fr: "Suites / item livré" },
  fusionItemsDelivered: { en: "Items delivered", fr: "Items livrés" },
  fusionSuiteRuns: { en: "Suites run", fr: "Suites exécutées" },
  fusionRequeues: { en: "Requeues / refunds", fr: "Requeues / remboursements" },
  fusionCanaryReverts: { en: "Canary reverts", fr: "Reverts canari" },
  fusionBatches: { en: "Batches / bisect reverts", fr: "Rafales / reverts bisect" },
  fusionInfraRetries: { en: "Infra retries", fr: "Reprises infra" },
  fusionVerdicts: { en: "Canary verdicts", fr: "Verdicts canari" },
};
