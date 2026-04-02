---
stepsCompleted: [1, 2, 3]
inputDocuments: ['C:\Dev\IA\AzureDevOps\skillforge-backend\CLAUDE.md', 'C:\Dev\IA\AzureDevOps\skillforge-backend\prompts\query-course_content-main.txt']
session_topic: 'Projets codables en ~3h par un Agent Harness v2, orientés AI Engineering, utiles au quotidien'
session_goals: 'Liste de projets concrets et utiles, avec une idée ancre: outil de création d évaluations pour boîte noire textuelle'
selected_approach: 'ai-recommended'
techniques_used: ['Morphological Analysis', 'Cross-Pollination']
ideas_generated: ['Meta-Harness Auto-Améliorant (écarté pour V2)', 'Eval Generator from Specs (RETENU)', 'SkillForge Multi-Agent Decomposer (application cible)']
context_file: ''
---

# Brainstorming Session Results

**Facilitateur:** Etienne
**Date:** 2026-03-26

## Session Overview

**Sujet:** Projets codables en ~3h par un Agent Harness v2, orientés AI Engineering
**Objectifs:** Liste de projets concrets, utiles, orientés code + AI engineering, complexité ~3h de run autonome

### Contraintes du projet idéal
- Centré code — le livrable est un outil/app fonctionnel
- AI Engineering — implique de la conception de systèmes IA (prompts, évals, pipelines, agents...)
- ~3h de run autonome — complexité full-stack compatible avec le harness v2 (Planner → Generator → Evaluator)
- Utile pour Etienne — pas un toy project, un vrai outil utilisable

### Idée ancre
> Un outil d'aide à la création d'évaluations pour une boîte noire textuelle (text in → text out)

### Configuration de session
- **Approche:** Recommandation IA de techniques adaptées au sujet

## Technique Selection

**Approche:** AI-Recommended Techniques
**Contexte d'analyse:** Projets AI engineering pour Agent Harness v2, focus sur utilité concrète

**Techniques recommandées:**

- **Morphological Analysis (Phase 1):** Cartographier systématiquement les dimensions du sujet (domaines, types d'outils, patterns harness, besoins) et croiser les axes pour générer 30-50+ combinaisons de projets
- **Cross-Pollination (Phase 2):** Importer des patterns de domaines inattendus (DevOps, game dev, cybersécurité, éducation...) pour injecter de l'originalité
- **Reverse Brainstorming (Phase 3):** Identifier le pire projet harness v2 possible pour révéler les critères cachés de qualité et filtrer les idées

**Rationale IA:** Séquence conçue pour maximiser la divergence (phases 1-2) puis converger naturellement (phase 3). La morphologie donne le volume, la cross-pollination la surprise, le reverse brainstorming le filtre.

## Technique Execution Results

### Morphological Analysis — Exploration des domaines

L'exploration par axes a rapidement convergé vers un concept META puissant plutôt qu'une liste plate de projets.

**Insight clé:** L'aspect "meta" — utiliser le pattern GAN (builder/evaluator) du harness v2 pour construire un outil qui AIDE à concevoir des systèmes AI, en miroir de l'architecture du harness lui-même.

### Idées générées et évaluées

**[Meta #1]: Le Harness Récursif (Auto-Améliorant)**
_Concept_: Un harness qui s'améliore lui-même en utilisant sa propre architecture GAN. Le Generator produit des variantes de config, l'Evaluator mesure la qualité, boucle itérative.
_Novelty_: Auto-amélioration observable — le produit EST la démo.
_Statut_: **ÉCARTÉ pour V1** — trop méta, pas de ground truth pour les évals du harness lui-même. À revisiter en V2.

**[Applied #1]: Eval Generator from Specs ← RETENU**
_Concept_: Outil top-down qui prend un prompt/PRD/requirements en entrée, extrait les règles individuelles, les clusterise, génère des judges LLM-as-a-judge par cluster, crée des datasets de test (socle + ciblé), et produit une eval suite exécutable intégrée Langfuse.
_Novelty_: GAP MARCHÉ CONFIRMÉ — tous les outils existants (Promptfoo, DeepEval, Langfuse, LangSmith, Braintrust) supposent que l'utilisateur SAIT déjà ce qu'il veut évaluer. Personne ne fait "specs → eval suite" automatiquement.
_Application immédiate_: Master prompt SkillForge (v28, ~35 règles extractibles) comme premier cobaye.

### Architecture retenue pour l'Eval Generator

```
PROMPT / PRD / Requirements
         │
         ▼
┌─────────────────────────┐
│ 1. EXTRACTION           │ Extraire les règles atomiques
│    ~35 règles           │ (explicites + implicites)
└────────┬────────────────┘
         ▼
┌─────────────────────────┐
│ 2. CLUSTERING AUTO      │ Grouper par thème sémantique
│    5-7 clusters         │ (embedding similarity)
└────────┬────────────────┘
         ▼
┌─────────────────────────┐
│ 3. GÉNÉRATION JUDGES    │ Un prompt de judge par cluster
│    avec rubric scorée   │ Score 1-5 par règle du cluster
└────────┬────────────────┘
         ▼
┌─────────────────────────┐
│ 4. GÉNÉRATION DATASET   │ Pour chaque règle :
│    taggé par cluster    │  - cas positifs
│                         │  - cas edge
│                         │  - cas adversarial
└────────┬────────────────┘
         ▼
┌─────────────────────────┐
│ 5. EXÉCUTION → MATRICE  │ Langfuse datasets + scores
│    Scénarios × Règles   │ Heatmap de conformité
└─────────────────────────┘
```

**Dataset en deux couches :**
- Socle partagé (30-50 scénarios génériques testant toutes les règles)
- Ciblé par règle (5-10 scénarios spécifiques stressant les edge cases)

**Deux modes d'opération :**
- Mode 1 : Evals fixes → optimise le build (hill-climbing architectural)
- Mode 2 : Co-évolution ReAct → les evals AUSSI mutent en observant le comportement

### Analyse du marché (gap confirmé)

| Outil | Ce qu'il fait | Ce qu'il ne fait PAS |
|---|---|---|
| Promptfoo | CLI eval + red-teaming, configs déclaratives | Écriture manuelle des test cases |
| DeepEval | Framework eval, génération synthétique depuis EXEMPLES | Part d'exemples, pas de specs (bottom-up) |
| Langfuse | Observabilité, LLM-as-judge, datasets | Config manuelle des eval prompts |
| LangSmith/OpenEvals | Evaluateurs prêts à l'emploi génériques | Pas de règles custom depuis specs |
| Braintrust | Dataset management + scoring + tracking | Définition manuelle des evals |

**Le chaînon manquant identifié:** Aucun outil ne fait du "top-down eval generation" (specs → eval suite).

### Prompt SkillForge analysé (cobaye idéal)

Prompt v28 — ~35 règles extractibles couvrant :
- Rôle & identité (personnalité, vouvoiement, ton)
- Langue de réponse (algorithme strict basé sur requête utilisateur)
- Sources & transparence (hiérarchie cours > connaissances)
- Structure de réponse (3 temps, longueur, format)
- Garde-fou périmètre (classification A-H obligatoire)
- Adaptation au niveau académique (niveaux 3-7)
- Format & markdown (obligatoire, gras, longueur)
- Éthique & contenus sensibles (refus catégorique)

## Creative Facilitation Narrative

Session caractérisée par une convergence rapide et organique. L'idée ancre d'Etienne (eval builder) s'est enrichie d'un concept META (GAN builder/evaluator) qui a d'abord pris une forme récursive (harness qui s'auto-améliore) avant de se recentrer pragmatiquement sur un terrain d'application concret (SkillForge). Le gap marché a été confirmé par recherche web. Le projet final combine originalité conceptuelle et utilité immédiate.
