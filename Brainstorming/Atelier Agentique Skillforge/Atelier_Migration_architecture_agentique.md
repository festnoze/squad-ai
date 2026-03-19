# Atelier : Migration vers une architecture agentique

**Objectif de l'atelier :** comprendre ce qu'est une architecture agentique, identifier pourquoi elle répond aux limites actuelles de Skillforge, et ressortir avec une liste de propositions concrètes d'agents par lesquels commencer — sans chercher à poser une architecture définitive.

**Format :** Workshop technique — 2h
**Prérequis :** Connaissance de l'archi actuelle (master prompt + modèle unique : GPT-4.1 Mini)

---

## MODULE 1 — C'est quoi une archi agentique ? *(20 min)*

**Objectif :** s'aligner sur le vocabulaire et les concepts avant de concevoir quoi que ce soit.

### Questions de lancement

- Quelle différence entre un chatbot à prompt unique et un agent ?
- Avez-vous déjà utilisé un outil qui vous semblait "agentique" ?

### Points théoriques si besoin

- **Définition :** un agent = LLM + mémoire + outils + boucle de raisonnement (ReAct, Plan-and-Execute…)
- **Les 3 composants clés :**
  - Orchestrateur (chef d'orchestre)
  - Agents spécialisés (sous-traitants)
  - Outils / Tools (actions sur le monde)
- **Patterns courants :** single-agent avec tools, multi-agents avec router, pipeline séquentiel, parallel dispatch
- **Frameworks de référence :** LangGraph, AutoGen, CrewAI, ou natif via Anthropic Tool Use / OpenAI function calling
- **Ce que ça N'est pas :** un simple enchaînement de prompts hardcodés — insister sur la **boucle de décision dynamique**

---

## MODULE 2 — Pourquoi pour Skillforge ? *(25 min)*

**Objectif :** rendre les limites du master prompt monolithique visibles et douloureuses.

### Questions à se poser

- Quelles tâches Skillforge fait mal ou de façon incohérente ?
- Quelles fonctionnalités sont aujourd'hui impossibles à ajouter sans tout casser ?

### Liste des limites

| Limite | Description |
|--------|-------------|
| **Context window saturée** | Cours + historique + instructions dans la même passe = dégradation |
| **Pas de spécialisation** | Un prompt qui fait tout fait tout moins bien |
| **Pas de mémoire long-terme** | L'apprenant repart de zéro à chaque cours / conversation |
| **Coût** | Injecter le cours entier à chaque requête + tout l'historique = coûteux |

---

## MODULE 3 — Quels agents pour Skillforge ? *(45 min)*

**Objectif :** co-construire une architecture adaptée à Skillforge, pas générique.

> !! Liste non exhaustive d'agents à discuter, à compléter ou à revoir !!

### Agents à discuter

| Agent | Rôle |
|-------|------|
| **Router** | Comprend l'intention, dispatch vers le bon agent |
| **Pedagogy Agent** | Explique le cours via RAG ou autre (plus de full context) |
| **Exercise Agent** | Génère des exercices, évalue, donne du feedback |
| **Memory Agent** | Profil apprenant persistant entre les sessions |

### Questions de design à trancher

- Quel modèle par agent ? *(léger pour le router, plus puissant pour la pédagogie ?)*
- Où vit la mémoire ? *(vector DB, SQL, profil JSON ?)*
- RAG ou chunking pour récupérer le contenu du cours ?

---

## MODULE 4 — Par où commencer *(30 min)*

**Objectif :** sortir avec une liste de propositions d'agents candidats pour une première brique, avec leurs avantages et risques associés — sans décision définitive.

### Principe de migration *(5 min)*

> **Règle d'or :** un agent à la fois, testé en **shadow mode** (parallèle à l'archi actuelle), validé, puis basculé.

### Propositions d'agents candidats pour démarrer *(25 min)*

Chaque proposition est à évaluer collectivement sur trois critères : **valeur perçue**, **complexité d'implémentation**, **risque**.

> !! Exemples de propositions se basant sur la précédente liste (pouvant être complétée et revue) !!

---

#### Proposition A — Router Agent en premier

| Critère | Évaluation |
|---------|------------|
| Ce que ça apporte | |
| Complexité | |
| Risque principal | |

---

#### Proposition B — Exercise Agent en premier

| Critère | Évaluation |
|---------|------------|
| Ce que ça apporte | |
| Complexité | |
| Risque principal | |

---

#### Proposition C — Memory Agent en premier

| Critère | Évaluation |
|---------|------------|
| Ce que ça apporte | |
| Complexité | |
| Risque principal | |

---

#### Proposition D — Pedagogy Agent + RAG en premier

| Critère | Évaluation |
|---------|------------|
| Ce que ça apporte | |
| Complexité | |
| Risque principal | |

---

## Livrables attendus en sortie d'atelier

- Liste des agents candidats **priorisés** par l'équipe
- Critères de choix **documentés**
- Prochaine session pour trancher et poser l'architecture
