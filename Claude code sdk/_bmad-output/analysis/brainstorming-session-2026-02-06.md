---
stepsCompleted: [1, 2, 3, 4]
inputDocuments: []
session_topic: 'Optimisation évolutive de workflows d agents pédagogiques'
session_goals: 'Concevoir un système multi-agents évolutif pour optimiser un chatbot pédagogique via algorithme génétique triple population'
selected_approach: 'ai-recommended'
techniques_used: ['Morphological Analysis', 'Cross-Pollination', 'Evolutionary Pressure']
ideas_generated: ['Architecture #1 - Algo Génétique Bi-Phasé', 'Architecture #2 - Triple Population Évolutive', 'Architecture #3 - Workflow Genome', 'Architecture #4 - TPE + Enrichissements', 'Architecture #5 - Évolution Hiérarchique Multi-Niveaux', 'Projet #1 - EduFlow Evolution']
context_file: ''
project_name: 'EduFlow Evolution'
---

# EduFlow Evolution — Optimisation Évolutive de Workflows Pédagogiques

**Facilitateur:** Etienne
**Date:** 2026-02-06
**Statut:** Concept validé — prêt pour spécification technique

---

## 1. Vision du Projet

**EduFlow Evolution** est un système d'optimisation évolutive qui fait co-évoluer des workflows d'agents IA pour maximiser la qualité de réponse d'un chatbot pédagogique. Le système utilise un algorithme génétique à triple population avec évaluation multi-critères à 19 dimensions.

**Objectif :** Trouver automatiquement la meilleure architecture d'agents (rôles, prompts, paramètres, routage) pour répondre aux questions d'apprenants sur un cours donné.

**Principe fondamental :** On ne cherche pas à optimiser un prompt unique, mais un **workflow complet d'agents** — leur nombre, leurs rôles, leurs prompts, leurs interconnexions, et leurs paramètres.

---

## 2. Architecture Globale

### 2.1 Les Trois Populations Co-Évolutives

```
┌─────────────────────────────────────────────────────────┐
│                    COUCHE 0 — GROUND TRUTH               │
│         ~50 paires (query, réponse attendue)             │
│              Validées humainement — NE MUTE JAMAIS       │
└──────────────────────┬──────────────────────────────────┘
                       │ calibre
          ┌────────────┼────────────┐
          ▼            ▼            ▼
   ┌─────────────┐ ┌─────────┐ ┌──────────────┐
   │ POPULATION B │ │ POP. A  │ │ POPULATION C │
   │ Évaluateurs  │ │Solutions│ │  Challenges  │
   │ (jugent A)   │◄┤(workflow│ │(queries adv.)│
   │              │ │d'agents)│ │ (testent A)  │
   └─────────────┘ └─────────┘ └──────────────┘
        │               ▲            │
        │  score         │            │
        └───────────────┘            │
              ▲    font échouer A     │
              └───────────────────────┘
```

| Population | Contenu | Objectif évolutif |
|------------|---------|-------------------|
| **A — Solutions** | Workflows d'agents (supervisor + sub-agents) | Maximiser la qualité de réponse pédagogique |
| **B — Évaluateurs** | Workflows d'évaluation multi-niveaux | Maximiser la corrélation avec le ground truth |
| **C — Challenges** | Queries / scénarios piégeux | Maximiser le taux d'échec de Population A |

### 2.2 Cycle d'une Génération

```
1. Population C génère des challenges (queries piégeuses)
2. Population A exécute les workflows sur les challenges de C
3. Population B évalue les résultats de A (3 niveaux)
4. CALIBRATION : vérification de B contre Couche 0 (ground truth)
   → Les évaluateurs mal calibrés perdent en fitness
5. SÉLECTION :
   - A : les workflows les mieux évalués par B survivent
   - B : les évaluateurs les mieux corrélés à Couche 0 survivent
   - C : les challenges qui discriminent le plus A survivent
6. REPRODUCTION : mutation + crossover pour A, B, et C
7. Nouvelle génération
```

---

## 3. Le Génome — Pattern Supervisor + Tools-as-Agents

### 3.1 Structure du Génome

Le génome d'un individu de Population A n'est PAS un prompt unique. C'est un **arbre supervisor** où chaque sub-agent est exposé comme un tool :

```
Individu (Workflow Genome)
│
├── Supervisor Agent
│   ├── system_prompt : texte libre (évoluable)
│   ├── params : {temperature, model, max_tokens}
│   ├── tools[] :
│   │   ├── Tool/SubAgent_1
│   │   │   ├── tool_card : description MCP (évoluable)
│   │   │   └── → Agent_1
│   │   ├── Tool/SubAgent_2
│   │   │   ├── tool_card : description MCP (évoluable)
│   │   │   └── → Agent_2
│   │   └── Tool/SubAgent_N
│   │       ├── tool_card : description MCP (évoluable)
│   │       └── → Agent_N
│   │
│   └── (récursif : un Agent peut avoir ses propres sub-agents)
│
├── Agent_1
│   ├── system_prompt : texte libre
│   ├── params : {temperature, model}
│   └── tools[] : [outils classiques ou sub-agents]
│
├── Agent_2 ...
└── Agent_N ...
```

### 3.2 Avantages du Pattern Supervisor

| Aspect | Bénéfice |
|--------|----------|
| **Routage** | Le LLM décide quel tool appeler — comportement émergent |
| **Edges = Tools** | Pas de DAG conditionnel explicite à maintenir |
| **Crossover** | Swap de tools entre supervisors = trivial |
| **Mutation** | Ajouter/retirer un tool = opération simple et safe |
| **Validité** | Vérification post-génération : pas de cycles, pas d'orphelins |

### 3.3 Composants Évoluables

| Composant | Type | Crossover | Mutation |
|-----------|------|-----------|---------|
| System prompt d'un agent | Texte libre | Par phrase/paragraphe | Reformulation, ajout, suppression |
| Tool cards (descriptions) | Texte libre | Par phrase | Affiner quand/comment utiliser l'agent |
| Liste de tools par agent | Ensemble discret | Swap de tools entre individus | Ajouter/retirer un tool |
| Params (temperature, model) | Numérique | Moyenne / choix aléatoire | Perturbation gaussienne |
| Arbre de hiérarchie | Structure | Swap de sous-arbres | Promouvoir/rétrograder un agent |

---

## 4. Dynamique Évolutive — Générationnel Bi-Phasé (D8)

### 4.1 Deux Phases

| Phase | Objectif | Mutation | Sélection | Durée |
|-------|----------|----------|-----------|-------|
| **Phase 1 — Exploration (Cambrienne)** | Diversité maximale | Taux élevé, crossover agressif | Permissive | ~60% des générations |
| **Phase 2 — Optimisation** | Convergence vers l'optimum | Taux faible, mutations fines | Élitiste | ~40% des générations |

### 4.2 Bascule Automatique

Le passage Phase 1 → Phase 2 est déclenché par un seuil de diversité ou de fitness :
- Quand la diversité de la population tombe sous un seuil → Phase 2
- Ou quand le top fitness stagne pendant N générations → Phase 2

---

## 5. Évaluation Multi-Niveaux — 19 Critères

### 5.1 Niveau 1 — MICRO (fragments, rapide, peu coûteux)

| # | Critère | Input | Mesure |
|---|---------|-------|--------|
| 1 | Toxicité de la question | Query seule | Classification binaire |
| 2 | Classification hors-sujet | Query + catégories | Classification multi-classe |
| 11 | Respect structure réponse | Réponse seule | Pattern matching + LLM |
| 17 | Absence sources externes | Réponse seule | Détection noms/URLs |
| 18 | Latence de réponse | Timestamps | Déterministe |
| 19 | Longueur de réponse | Réponse seule | Déterministe |

### 5.2 Niveau 2 — MÉSO (agent individuel)

| # | Critère | Input | Mesure |
|---|---------|-------|--------|
| 3 | Pertinence au domaine | Query + matière | LLM-juge |
| 4 | Pertinence au cours | Query + contenu cours | LLM-juge + RAG |
| 8 | Pertinence de la réponse | Query + réponse | LLM-juge |
| 12 | Adaptation niveau académique | Réponse + niveau apprenant | LLM-juge |
| 13 | Prise en compte texte sélectionné | Texte sélectionné + réponse | LLM-juge |
| 14 | Prise en compte quick action | Action + réponse | LLM-juge |
| 15 | Respect du périmètre | Query catégorisée + réponse | LLM-juge |

### 5.3 Niveau 3 — MACRO (workflow complet + contexte global)

| # | Critère | Input | Mesure |
|---|---------|-------|--------|
| 5 | Fidélité au contexte (Faithfulness) | Réponse + cours complet | LLM-juge profond |
| 6 | Complétude | Réponse + toutes sources cours | LLM-juge + vérification exhaustive |
| 7 | Groundedness (ratio cours/général) | Réponse + analyse ratio | LLM-juge analytique |
| 9 | Citation des sources | Réponse + marqueurs | LLM-juge + pattern |
| 10 | Détection hallucinations | Réponse + cours + faits | LLM-juge adversarial |
| 16 | Qualité pédagogique | Réponse + préconisations | LLM-juge expert pédagogie |

### 5.4 Vecteur de Fitness (19 dimensions)

```python
fitness_vector = {
    # Niveau 1 — MICRO
    "toxicity_detection":       float,  # 0.0 - 1.0
    "off_topic_classification": float,
    "response_structure":       float,
    "no_external_sources":      float,
    "latency_ms":               int,    # millisecondes
    "response_length":          float,  # score normalisé

    # Niveau 2 — MÉSO
    "domain_relevance":         float,
    "course_relevance":         float,
    "answer_relevancy":         float,
    "academic_adaptation":      float,
    "selected_text":            float,
    "quick_action":             float,
    "scope_compliance":         float,

    # Niveau 3 — MACRO
    "faithfulness":             float,
    "completeness":             float,
    "groundedness":             float,
    "source_citation":          float,
    "hallucination_free":       float,
    "pedagogical_quality":      float,
}
```

### 5.5 Pondération par Phase

- **Phase Exploration** : toutes dimensions pondérées également
- **Phase Optimisation** : pondération forte sur critères macro (fidélité, hallucinations, pédagogie) — les critères micro devraient être résolus

---

## 6. Mécanismes d'Enrichissement

### 6.1 M1 — Télémétrie d'Exécution

**Source :** Analogie Formule 1

Tracer l'exécution de chaque agent dans le workflow pour comprendre **pourquoi** une solution gagne :
- Logging de chaque tool call du supervisor
- Temps passé par agent
- Tokens consommés par agent
- Qualité de sortie par agent (évaluation méso)

**Utilité :** Permet un crossover intelligent — on identifie quel sous-composant est performant et on le transplante dans d'autres individus.

### 6.2 M3 — Jurisprudence Évolutive

**Source :** Analogie Système Judiciaire

Registre persistant des évaluations passées :
- Quand un évaluateur juge un nouveau cas, il peut consulter des cas similaires déjà tranchés
- Stabilise l'évaluation au fil des générations
- Empêche les régressions (un pattern déjà jugé mauvais ne peut pas revenir comme bon)

### 6.3 M6 — Profil Multi-Critères

**Source :** Analogie Startup (Due Diligence)

Pas un score unique mais un vecteur de fitness à 19 dimensions :
- Permet la sélection multi-objectifs (Pareto)
- La pondération change entre phases (exploration vs optimisation)
- Rend le cycling Red Queen beaucoup plus difficile sur 19 dimensions simultanées

---

## 7. Gardes-fous de Convergence

| Mécanisme | Protège contre |
|-----------|---------------|
| Couche 0 (ground truth) | Dérive des évaluateurs |
| Phase bi-phasée (D8) | Convergence prématurée (phase 1) et stagnation (phase 2) |
| Jurisprudence (M3) | Oscillations et régressions |
| Fitness 19D (M6) | Cycling Red Queen sur une seule dimension |

---

## 8. Bootstrap — Séquence de Démarrage

| Étape | Action | Résultat |
|-------|--------|----------|
| **Boot 0** | L'humain fournit ~50 paires (query apprenant, réponse attendue) sur un cours réel | Couche 0 (gold standard) |
| **Boot 1** | Génération aléatoire — Pop. A : workflows naïfs (1 supervisor + 1-3 agents), Pop. B : évaluateurs simples ("compare au gold standard"), Pop. C : queries du gold standard | Premières populations |
| **Boot 2** | Première génération — les workflows sont mauvais mais le cycle tourne | Évolution enclenchée |

---

## 9. Référence — Papier GAAPO

**Source :** "GAAPO: Genetic Algorithmic Applied to Prompt Optimization" (Sécheresse, Guilbert-Ly, Villedieu de Torcy — Biolevate, 2025)

**Éléments intégrés :**
- 5 stratégies de mutation hybrides (pas juste du random) : APO, OPRO, Random Mutator, Crossover, Few-shot
- Le crossover de prompts fonctionne (split au point médian ou par phrase)
- Trade-off taille de population vs nombre de générations
- Risque d'overfitting au dataset de validation → atténué par notre Couche 0 + jurisprudence

**Différences avec GAAPO :**
- GAAPO optimise des prompts uniques → nous optimisons des **workflows d'agents complets**
- GAAPO a une seule population → nous avons **triple population co-évolutive**
- GAAPO utilise un score unique → nous utilisons un **vecteur 19D**

---

## 10. Population C — Exemples de Challenges Adversariaux

Types de queries piégeuses que Pop. C peut générer :

| Type | Exemple | Critère ciblé |
|------|---------|---------------|
| Toxicité déguisée | "Comment pirater le système de notes ?" | #1 Toxicité |
| Hors-sujet subtil | "Quel est le lien entre ce cours et la politique ?" | #2, #15 Classification |
| Réponse absente du cours | "Que dit le cours sur [sujet non couvert] ?" | #4, #7 Pertinence/Groundedness |
| Ambiguïté avec texte sélectionné | Texte sélectionné contredit la question | #13 Texte sélectionné |
| Quick action contradictoire | Quick action "résumer" sur une question de détail | #14 Quick action |
| Piège à hallucination | Question plausible mais la bonne réponse est contre-intuitive | #10 Hallucinations |

---

## 11. Récapitulatif des Décisions

| Décision | Choix | Raison |
|----------|-------|--------|
| Architecture | Triple Population Co-Évolutive | Compétition + évaluation + challenges adversariaux |
| Génome | Arbre Supervisor + Tools-as-Agents | Crossover trivial, routage émergent, validité vérifiable |
| Dynamique | Générationnel Bi-Phasé (D8) | Rigueur d'évaluation + adaptation mutation rate |
| Domaine | Chatbot pédagogique (B2 appliqué) | 19 critères mesurables, gold standard bootstrapable |
| Évaluation | Multi-niveaux (micro/méso/macro) × 19 critères | Granularité + parallélisme + ciblage |
| Enrichissements | M1 (télémétrie) + M3 (jurisprudence) + M6 (fitness 19D) | Crossover intelligent + stabilité + sélection multi-objectifs |
| Économie tokens | Pas de sampling — on brûle du token | Objectif assumé |

---

## 12. Prochaines Étapes

1. **Spécification technique** — Stack, architecture code, format du génome
2. **Construction du Gold Standard** — 50 paires (query, réponse) sur un cours réel
3. **Prototype minimal** — 1 génération avec Pop. A (5 individus), Pop. B (3 évaluateurs), Pop. C (10 queries)
4. **Itération** — Augmenter progressivement la complexité

---

*Document généré lors de la session de brainstorming du 2026-02-06*
*Techniques utilisées : Analyse Morphologique, Cross-Pollination, Pression Évolutive*
*Facilitateur : BMad Master 🧙*
