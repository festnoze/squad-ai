# Plan — Software Factory Agentique Auto‑Adaptative

## 1. Vision

Construire une software factory *spec-driven* capable d'évoluer progressivement :

- Human-in-the-Loop
- Human-on-the-Loop
- Human-out-of-the-Loop

sans modifier la structure du workflow.

Le workflow est invariant ; seule la politique d'exécution change.

---

# 2. Principes fondateurs

- Séparation stricte des responsabilités.
- Les agents produisent des artefacts et des preuves.
- Aucun agent ne valide son propre travail.
- Toute décision est traçable.
- Toute découverte peut faire évoluer le backlog.
- Le système apprend en continu.

---

# 3. Cycle global

Intent

↓

Discovery

↓

Specification

↓

Planning

↓

Architecture

↓

Technical Planning

↓

Implementation

↓

Verification

↓

Review

↓

Release

↓

Observation

↓

Learning

↓

Replanning

---

# 4. Politique d'autonomie

Deux notions :

- Recommended Autonomy
- Effective Autonomy

Niveaux :

0 Human only

1 AI proposes

2 AI executes + Human validates

3 AI executes + Human reviews

4 AI executes + Judges validate

5 Full autonomy

Un Policy Engine décide du niveau réellement appliqué.

---

# 5. Boucle de développement

## Codebase Cartographer

Construit une carte locale du code :

- composants
- dépendances
- conventions
- fichiers concernés
- risques

## Technical Planner

Transforme une tâche fonctionnelle en plan technique.

## Test Designer

Construit la stratégie de validation :

- unit tests
- integration tests
- edge cases
- negative tests
- regression

## Coding Agent

Produit :

- code
- tests
- preuves
- observations

## Failure Analyst

Diagnostique les échecs :

- bug
- test incorrect
- ambiguïté
- problème d'architecture

## Refactoring Agent

Améliore la structure après stabilisation.

## Integration Agent

Vérifie l'intégration globale.

---

# 6. Boucle d'évaluation

## Evaluators

- Acceptance Evaluator
- Regression Evaluator
- Architecture Evaluator
- Security Evaluator
- Maintainability Evaluator
- Specification Conformance Judge
- Adversarial Reviewer
- Evidence Auditor

## Decision Aggregator

Agrège les verdicts.

Décisions possibles :

- Retry implementation
- Revise technical plan
- Revise task
- Revise story
- Revise feature
- Abort
- Complete

---

# 7. Observation Engine

Chaque tâche produit deux sorties.

## Delivery Result

- code
- diff
- commit
- preuves
- tests

## Engineering Observations

Exemples :

- workaround
- dette technique
- risque
- limitation
- refactoring
- amélioration possible
- ambiguïté
- contrainte découverte

---

# 8. Engineering Observation

Une observation contient :

- type
- résumé
- description
- preuves
- impact
- confiance
- urgence
- workaround
- recommandations
- conditions de réévaluation

---

# 9. Observation Router

Route les observations vers :

- PO Agent
- Architecture Agent
- Security Agent
- SRE Agent
- Technical Debt Agent
- Product Discovery Agent

Le Coding Agent observe.

Il ne décide pas de la roadmap.

---

# 10. PO comme Backlog Governor

Le PO décide :

- créer une tâche
- modifier une US
- modifier une Feature
- créer une Epic
- enrichir les critères d'acceptation
- ignorer
- persister
- reporter

---

# 11. Mémoire multi‑niveaux

Une observation peut être persistée dans :

- mémoire de tâche
- mémoire composant
- mémoire architecture
- ADR
- registre de dette
- registre de risques
- backlog

Toutes les observations ne deviennent pas des tâches.

---

# 12. Pattern Detector

Agent ambient chargé de :

- détecter les tendances
- regrouper les observations
- identifier les composants problématiques
- proposer des refactorings globaux
- détecter les accumulations de dette

---

# 13. Ambient AI

Architecture événementielle.

Les agents sont réveillés uniquement lorsqu'un événement pertinent apparaît.

Pas de boucle LLM permanente.

---

# 14. Conversation inter‑agents

Coding Agent

↓

Engineering Observation

↓

Observation Critic

↓

Observation Router

↓

Agents spécialisés

↓

PO / Governance

↓

Backlog mis à jour

---

# 15. Gouvernance

Agents complémentaires :

- Strategy Agent
- Governance Agent
- Portfolio Agent
- Budget Authority
- Risk Authority
- Factory Auditor
- Meta Evaluator

---

# 16. Product Discovery

Compléter la factory avec :

- Analytics Agent
- User Feedback Agent
- Experiment Agent
- Product Value Judge

Objectif :

Passer de

"Construire correctement"

à

"Construire ce qui apporte réellement de la valeur".

---

# 17. Exploitation

Compléter avec :

- Release Agent
- Platform Agent
- SRE Agent
- Incident Agent
- Cost Optimizer

---

# 18. Vision long terme

Software Factory

↓

Adaptive Software Factory

↓

Autonomous Software Organization

Le système devient capable de :

- planifier
- construire
- tester
- évaluer
- observer
- apprendre
- replanifier
- améliorer son propre workflow

sans modifier son architecture générale.

---

# 19. Principe clé

Une tâche ne produit plus seulement un incrément logiciel.

Elle produit également :

- des preuves
- des observations
- de nouvelles connaissances
- des propositions d'évolution
- des mises à jour potentielles du backlog

Le cycle devient :

Code

↓

Tests

↓

Observations

↓

Analyse

↓

Réécriture du backlog

↓

Nouvelle planification

---

# 20. Questions ouvertes

- Comment mesurer la valeur réelle d'une feature ?
- Quand une observation devient-elle une tâche ?
- Comment limiter les discussions inter‑agents ?
- Comment versionner la mémoire du projet ?
- Comment évaluer les évaluateurs ?
- Comment faire évoluer la gouvernance elle-même ?
- Quels critères déclenchent une replanification globale ?
