# Atelier : Migration vers une architecture agentique

**Objectif de l'atelier :** comprendre ce qu'est une architecture agentique, identifier pourquoi elle répond aux limites actuelles de Skillforge, et ressortir avec une liste de propositions concrètes d'agents par lesquels commencer — sans chercher à poser une architecture définitive.

**Format :** Workshop technique — 2h
**Prérequis :** Connaissance de l'archi actuelle (master prompt + modèle unique : GPT-4.1 Mini)

---

## MODULE 1 — C'est quoi une archi agentique ? *(20 min)*

**Objectif :** s'aligner sur le vocabulaire et les concepts avant de concevoir quoi que ce soit.

### Questions de lancement

**Q : Quelle différence entre un chatbot à prompt unique et un agent ?**

Un chatbot classique reçoit un message, génère une réponse, s'arrête. Il ne peut ni décider seul d'une prochaine action, ni appeler un outil, ni déléguer.

Un agent apporte plusieurs choses :

**1. Une boucle de raisonnement (ReAct)**
L'agent peut enchaîner : agir → observer le résultat → réajuster → agir à nouveau. Il décide lui-même quand il a fini. C'est ça le vrai marqueur : la boucle de décision dynamique.

**2. Un découpage des responsabilités**
Aujourd'hui dans Skillforge, le master prompt porte tout : respect de la langue, contextualisation de la question avec l'historique, adaptation au niveau académique de l'apprenant, ton pédagogique, etc. L'architecture agentique permet d'éclater ces responsabilités vers des agents ou outils spécialisés — chacun fait une chose, bien. On applique le SRP au niveau de l'IA.

**3. Une puissance adaptative via les outils et la classification**
Un agent classifieur peut analyser la nature de chaque requête et router vers l'agent le plus adapté — voire vers un modèle plus ou moins puissant ou avec mode thinking, selon la complexité de la question. Une question simple va vers un modèle léger, une question pédagogique complexe vers un modèle plus capable. Economique, car le cout de revient est fonction de la complexité de la réponse.
---

**Q : Avez-vous déjà utilisé un outil qui vous semblait "agentique" ?**

Exemples concrets pour ancrer le concept :
- **Cursor / Copilot Workspace** : lit des fichiers, modifie du code, relance des tests — boucle autonome
- **Devin** : planifie, code, debug, itère
- **Agents Langchain avec outils: browsing et code interpreter** : décide seul quand appeler l'outil

---

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

### Affirmations à retenir

- L'agent ne remplace pas le LLM, il l'encadre. Le modèle reste le moteur de raisonnement, l'architecture agentique lui donne des rails et des leviers d'action.
- La boucle de décision est le vrai marqueur — si le système ne peut pas décider seul de sa prochaine action, c'est un pipeline, pas un agent.

### Questions ouvertes

- Où place-t-on le curseur d'autonomie ? Un agent qui agit sans validation humaine est risqué. Quel niveau d'approbation veut-on garder dans Skillforge ?
- Quel est le coût d'un "bad loop" ? Si un agent se trompe et boucle, qui détecte et coupe ?

---

## MODULE 2 — Pourquoi pour Skillforge ? *(25 min)*

**Objectif :** rendre les limites du master prompt monolithique visibles et douloureuses.

---

**Q : Quelles tâches Skillforge fait mal ou de façon incohérente ?**

Le modèle est petit, le contexte est large (cours entier + historique + instructions). Cette combinaison dégrade mécaniquement la qualité des réponses — un modèle focusé sur une tâche découpée avec un contexte ciblé ferait mieux.

---

**Q : Quelles fonctionnalités sont aujourd'hui impossibles à ajouter sans tout casser ?**

Le prompt est à saturation. Chaque nouvelle instruction (ex : respect de la langue de l'utilisateur ≈ 10 lignes) dilue les instructions existantes. On ne peut plus garantir un suivi égal de toutes les règles, et tout ajout crée un risque de régression sur le reste — les instructions sont fortement interdépendantes, pas isolées.

---

### Limites justifiant le passage aux agents

| Limite | Description |
|--------|-------------|
| **Context window saturée** | Cours + historique + instructions dans la même passe = dégradation de la qualité de suivi des instructions |
| **Pas de spécialisation** | Un prompt qui fait tout fait tout moins bien — la qualité de chaque aspect souffre de la cohabitation |
| **Prompt monolithique = risque d'interdépendance** | Chaque ajout de fonctionnalité vient potentiellement dégrader la qualité du suivi des autres instructions |

**Preuve concrète de saturation : la règle de langue dupliquée**

Dans le prompt v28, la règle "LANGUE DE RÉPONSE" est écrite **deux fois**. Ce n'est pas un oubli : elle a dû être répétée parce que le modèle ne la respectait plus de façon fiable dans un prompt aussi chargé. C'est la dilution en action, documentée dans le code.

**Ce que l'architecture agentique permettrait concrètement ici :**
- Un **routing explicite** vers un outil dédié à la détection de langue, qui retire définitivement cette responsabilité du prompt principal — et la rend déterministe.
- Des **réponses prédéfinies sans LLM** pour les cas de refus : la classification A→H embarquée dans le prompt contient 4 cas de refus (C — scolarité, D — support technique, F — vidéo, H — live) qui génèrent des réponses fixes. Aujourd'hui, un LLM complet est consommé pour décider de renvoyer une phrase statique. Un agent de routing léger en tête de pipeline supprimerait ce coût entièrement.

---

### Contraintes techniques à adresser (hors périmètre agentique strict)

Les points suivants sont des problèmes réels mais ne sont pas des arguments *pour* les agents en soi — ce sont des contraintes de design à traiter indépendamment :

| Contrainte | Note |
|------------|------|
| **Mémoire long-terme** | Se résout avec une bonne architecture de stockage (SQL, vector DB). Les agents peuvent *utiliser* cette mémoire, pas la créer. |
| **Coût** | Dépend d'abord des choix de modèles et de chunking, pas de l'architecture agentique elle-même. |

---

### Remarque clé : l'agentivité comme "enabler"

L'architecture agentique ne résout pas directement les problèmes de mémoire ou de récupération de contexte — elle crée les conditions pour que des solutions spécialisées (RAG, episodic memory, chunking) puissent être branchées proprement, chacune dans son périmètre.

---

## MODULE 3 — Quels agents pour Skillforge ? *(45 min)*

**Objectif :** co-construire une architecture adaptée à Skillforge, pas générique.

---

### Remarque préliminaire : architecture hybride

Ce qui se dessine n'est pas purement agentique — c'est un **workflow avec des boucles agentiques embarquées**. Certaines étapes sont séquentielles et déterministes (pré-traitement), d'autres sont des boucles de type ReAct (recherche → évaluation → re-recherche). Les deux coexistent, et c'est sain.

> **Note de cadrage :** En toute rigueur, ce système devrait être nommé **"workflow modulaire supervisé avec boucle RAG réflexive"** plutôt qu'une "architecture agentique" au sens strict. La valeur réelle vient du découpage des responsabilités (SRP appliqué à l'IA) et de la modularité — pas de l'autonomie des agents. L'agentivité est concentrée là où elle a le plus de sens : la recherche de contexte. C'est un choix délibéré : dans un contexte pédagogique de production, la prévisibilité de la qualité prime sur l'autonomie.

---

### Analyse du prompt actuel (v28) — Responsabilités identifiées

#### Observation symptomatique

La règle "LANGUE DE RÉPONSE" est écrite **deux fois** dans le prompt. C'est le signe le plus concret du problème de prompt monolithique : on a dû répéter l'instruction parce que le modèle ne la respectait pas dans un contexte aussi chargé. C'est exactement la dilution décrite en Module 2 — vivante dans le code.

#### Mapping des sections du prompt → agents/outils

| Section du prompt | Responsabilité | Agent/Outil cible |
|---|---|---|
| Rôle et identité | Persona, ton, vouvoiement, posture pédagogique | **Pedagogy Agent** (prompt épuré) |
| Contexte et données disponibles | Assemblage des inputs (historique, cours, niveau, breadcrumb, texte sélectionné, action rapide) | **Context Builder** *(workflow)* |
| LANGUE DE RÉPONSE (×2) | Détection de la langue de la requête | **Language Detector** *(outil déterministe — retire 30+ lignes)* |
| Principe de réponse / sources | Hiérarchie cours → connaissances générales, règles de citation | **Pedagogy Agent** |
| Structure de réponse | 3 temps conversationnels, règles de salutation, longueur | **Pedagogy Agent** |
| **Garde-fou / classification A→H** | Routing selon l'intention : 8 catégories, réponses prédéfinies pour les refus | **Router / Intent Classifier** |
| Adaptation au niveau académique | 5 niveaux européens, adaptation vocabulaire/complexité, `{{academic_level}}` | **Profile Tool** + **Pedagogy Agent** |
| Règles de citation et limites | Pas de liens externes, contenu manquant | **Pedagogy Agent** |
| Contraintes de format | 500 tokens, phrases courtes, emojis | **Pedagogy Agent** |
| Mise en forme Markdown | Éléments autorisés, bonnes pratiques de structuration | **Pedagogy Agent** |
| **Éthique et contenus sensibles** | Refus de contenu discriminatoire/extrémiste | **Guardrail Agent** *(filtre indépendant)* |
| Contexte du cours `{{lesson_breadcrumb}}` | Fil d'Ariane hiérarchique | **Context Builder** |
| **Contenu du cours `{{lesson_content}}`** | Cours injecté en entier à chaque requête | **RAG Tool** *(remplacement majeur)* |
| Objectif final | Dialogue intelligent, encouragement, autonomie | **Pedagogy Agent** |
| `{{personalization_instructions}}` | Instructions de personnalisation apprenant | **Profile Tool** / Memory |

#### Deux points particulièrement saillants

**1. La classification A→H est un Router déguisé dans le prompt**
8 catégories, des réponses prédéfinies pour les refus (C, D, F, H), des conditions pour les cas intermédiaires (E, G). Aujourd'hui on dépense un LLM complet pour faire ce routing — un modèle léger dédié le ferait mieux, plus vite, et sans polluer le prompt du Pedagogy Agent.

**2. `{{lesson_content}}` est le problème n°1 de coût et de qualité**
Le cours entier est injecté à chaque requête. C'est la raison principale de la saturation de context window. Un RAG Tool avec escalade progressive remplacerait cela avec un contexte ciblé et pertinent.

---

### Découpage des responsabilités — flux de traitement

> **Note :** Le fil d'Ariane (`{{lesson_breadcrumb}}`), le texte sélectionné et l'action rapide sont des éléments natifs de la requête — ils font partie du contexte naturel de la demande et ne transitent par aucun agent de transformation.

**Étape 1 — Guardrails & Intent Classification** *(agent léger, premier filtre)*

Premier point d'entrée : avant tout traitement, on vérifie si la requête est traitables et on route.

Porte :
- Détection de toxicité et filtre éthique *(section "Éthique" du prompt actuel)*
- Classification de l'intention A→H *(section "Garde-fou" du prompt actuel)*

| Catégorie | Type | Action |
|---|---|---|
| A — Question sur le cours | AUTORISÉ | → Pipeline pédagogique |
| B — Erreur dans le cours | AUTORISÉ | Réponse prédéfinie *(sans LLM)* |
| C — Scolarité / administratif | REFUS | Réponse prédéfinie *(sans LLM)* |
| D — Support technique | REFUS | Réponse prédéfinie *(sans LLM)* |
| E — Auto-évaluation | AUTORISÉ SOUS CONDITION | → Pedagogy Agent *(mode spécifique)* |
| F — Question sur vidéo | REFUS | Réponse prédéfinie *(sans LLM)* |
| G — Quiz / Exercice | AUTORISÉ SOUS CONDITION | → Exercise Agent |
| H — Live | REFUS | Réponse prédéfinie *(sans LLM)* |
| Toxique / éthique | REFUS | Réponse prédéfinie *(sans LLM)* |

**Étape 2 — Query Intelligence** *(semi-agentique)*

- **History Contextualized Query** : contextualise la question courante avec l'historique de conversation — reformule la requête brute en une question autonome et complète
- **Profile Tool** : récupère le niveau académique et le parcours suivi de l'apprenant (`{{academic_level}}`, `{{personalization_instructions}}`)
- **Language Detector** : détection déterministe de la langue sur la requête utilisateur uniquement
- **Query Rewriter** : reformulation orientée données pour le RAG, peut inclure HyDE *(générer une réponse hypothétique, puis chercher par similarité avec elle)*
- **Query Decomposer** : si la question est complexe, la fragmenter en sous-questions atomiques, chacune traitable indépendamment avec potentiellement des sources différentes, avant synthèse finale

**Étape 3 — Recherche de contexte avec boucle évaluateur** *(agentique — cœur du ReAct)*

C'est ici que la boucle agentique s'exprime — elle remplace l'injection du `{{lesson_content}}` complet :

```
Recherche → Évaluation (pertinence + suffisance ?) → si non → Recherche élargie → ...
```

Escalade progressive de la granularité :
1. Leçon courante
2. Thème
3. Module
4. Matière
5. En dernier recours : sources externes (recherche internet, MCP Studi)

L'**Evaluator Agent** est le pivot : il juge si les éléments trouvés sont pertinents et suffisants. Si non, il déclenche une nouvelle passe à un niveau plus large.

**Étape 4 — Synthèse et génération** *(workflow)*
- Agrégation des réponses aux sous-questions
- Génération de la réponse finale par le Pedagogy Agent avec son prompt épuré

---

### Tableau agents/outils — architecture cible

| Agent / Outil | Type | Rôle |
|---|---|---|
| **Guardrails & Intent Classifier** | Agent léger | Filtre éthique + toxicité + classification A→H → réponses prédéfinies ou routing |
| **History Contextualized Query** | Outil | Contextualise la requête courante avec l'historique de conversation |
| **Profile Tool** | Outil | Récupère niveau académique et parcours suivi de l'apprenant |
| **Language Detector** | Outil déterministe | Détecte la langue de la requête utilisateur |
| **Query Rewriter** | Outil | Reformule la requête pour le RAG, incl. HyDE |
| **Query Decomposer** | Agent | Décompose les questions complexes en sous-questions atomiques |
| **RAG Tool** | Outil | Recherche dans les cours à granularité progressive (leçon → matière) |
| **Evaluator Agent** | Agent | Juge pertinence + suffisance → déclenche ou non une nouvelle passe |
| **External Search Tool** | Outil | Internet / MCP Studi en dernier recours |
| **Synthesis Agent** | Agent | Agrège les réponses des sous-questions |
| **Pedagogy Agent** | Agent principal | Génère la réponse finale — prompt épuré, focusé sur la pédagogie |
| **Exercise Agent** | Agent | Quiz, exercices, auto-évaluation (catégories E et G) |

---

### Pistes pour renforcer l'agentivité utile, sans sur-risque

**Piste 1 — Orchestrateur adaptatif**
Plutôt qu'un pipeline fixe, un orchestrateur léger décide quelles étapes activer selon la nature de la requête. Une question factuelle courte saute le Query Decomposer et le HyDE. Une question manifestement couverte par la leçon courante saute l'escalade. Cela ajoute de l'adaptivité sans toucher au cœur de la génération ni introduire d'indétermination sur la qualité de la réponse finale.

**Piste 2 — Auto-évaluation du Pedagogy Agent**
Après avoir produit un brouillon de réponse, le Pedagogy Agent évalue si sa réponse couvre bien la question posée — et si non, peut déclencher une passe de récupération de contexte supplémentaire. C'est un ReAct léger, borné à 1-2 itérations maximum, sur une étape à faible risque de dérive.

**Piste 3 — Exercise Agent comme bac à sable agentique** *(horizon)*
L'Exercise Agent est le candidat idéal pour une boucle agentique plus libre : générer → évaluer la difficulté par rapport au niveau de l'apprenant → ajuster → valider. Les enjeux y sont plus faibles (un exercice imparfait se corrige), ce qui en fait un terrain d'expérimentation sûr pour le pattern avant de l'étendre au pipeline principal.

---

### Questions de design à trancher

- L'Evaluator Agent : LLM à part entière ou scoring déterministe (seuil de similarité) ? Quel coût acceptable par passe ?
- HyDE : qui génère l'hypothèse ? Avec quel modèle ?
- Escalade : automatique sur seuil de confiance, ou configurable par type de question ?
- La décomposition de requête complexe : comment détecter qu'une question est "complexe" ? Classifier en amont ou laisser l'agent décider ?
- Mémoire épisodique : quels critères pour décider quels éléments de l'historique injecter ?
- Le Language Detector : bibliothèque déterministe (langdetect, fastText) ou passe LLM légère ?
- Orchestrateur adaptatif : règles explicites ou modèle de décision léger ? Qui définit les conditions de saut d'étape ?

---

## MODULE 4 — Par où commencer *(30 min)*

**Objectif :** sortir avec une feuille de route de migration concrète par lots, chaque lot étant validé avant le suivant — sans décision définitive sur l'architecture finale.

### Principe de migration *(5 min)*

> **Règle d'or :** un lot à la fois, validé contre le dataset et les évaluateurs du Lot 1, puis basculé.

**Méthode de validation :** pour chaque bascule, deux niveaux de contrôle complémentaires :

- **Évaluation humaine** sur un échantillon représentatif — un expert pédagogique revoit les réponses produites par la nouvelle architecture et les note selon les dimensions du dataset
- **Exécution automatisée du dataset du Lot 1** avec les évaluateurs dédiés — les évaluateurs vérifient le respect des règles vérifiables (langue, routing, refus, format) et notent la qualité pédagogique des réponses

Les deux niveaux sont complémentaires : les évaluateurs automatiques assurent l'exhaustivité (toutes les questions du dataset) et la reproductibilité ; l'évaluation humaine couvre la nuance et la qualité pédagogique fine que les évaluateurs automatiques ne capturent pas entièrement.

---

### Stratégie de migration — lots d'implémentation *(25 min)*

Vue d'ensemble de la feuille de route :

- **Lot 1** — Dataset d'évaluation, baseline et évaluateurs *(prérequis absolu, avant tout changement)*
- **Lot 2** — Découpage des responsabilités + orchestrateur de workflow *(même comportement, architecture modulaire)*
- **Lot 3** — Infrastructure vectorielle + RAG simple non-itératif *(premier gain qualité et coût)*
- **Lot 4** — Query Intelligence avancée + RAG réflexif ReAct *(qualité sur questions complexes)*
- **Lot 5** — Exercise Agent *(horizon, traitement propre des catégories E et G)*

---

#### Lot 1 — Dataset d'évaluation, baseline et évaluateurs *(prérequis absolu)*

Avant de toucher quoi que ce soit au système, construire le filet de sécurité. Ce dataset et ces évaluateurs deviennent le référentiel de non-régression pour tous les lots suivants — chaque bascule est validée contre eux.

**Contenu du dataset — questions couvrant :**
- Toutes les catégories A→H avec cas limites par catégorie
- Toutes les langues supportées (FR, EN, ES minimum)
- Tous les niveaux académiques (3 à 7 européen)
- Questions simples vs complexes multi-concepts
- Questions avec texte sélectionné vs sans, avec action rapide vs sans
- Cas de refus : toxicité, contenu hors périmètre

**Évaluateurs à construire :**

Deux familles d'évaluateurs, selon la nature de ce qui est vérifié :

- **Évaluateurs déterministes** — pour les règles vérifiables mécaniquement, sans ambiguïté :
  - *Langue* : détection automatique de la langue de la réponse et comparaison avec la langue de la requête
  - *Routing intent* : vérification que la catégorie A→H détectée correspond à la catégorie attendue du dataset
  - *Réponses prédéfinies* : vérification que les catégories de refus (B, C, D, F, H, toxique) déclenchent bien la réponse prédéfinie exacte, sans variation
  - *Format Markdown* : vérification de la présence/absence des éléments attendus (titres, listes, longueur maximale)

- **Évaluateurs LLM-as-judge** — pour la qualité subjective qui ne peut pas être vérifiée mécaniquement :
  - *Respect du niveau académique* : le vocabulaire et la profondeur sont-ils adaptés au niveau de l'apprenant ?
  - *Complétude pédagogique* : la réponse couvre-t-elle bien la question posée, sans omission majeure ?
  - *Qualité pédagogique globale* : note synthétique (ex. 1-5) sur la clarté, la structure et l'utilité de la réponse

**Livrable :** dataset annoté + évaluateurs opérationnels + scores baseline du système actuel par dimension.

---

#### Lot 2 — Découpage des responsabilités + orchestrateur de workflow

**Objectif :** même comportement observable, architecture modulaire. Aucune nouvelle technologie (pas de vector DB, pas de RAG).

**Ce qui est implémenté :**
- **Orchestrateur de workflow** : code explicite et séquentiel — pas un LLM qui décide, pas d'ambiguïté sur l'ordre des étapes
- **Guardrails & Intent Classifier** : prompt spécialisé sur la classification A→H + toxicité → réponses prédéfinies directes pour B, C, D, F, H et cas toxiques, sans consommer le LLM principal
- **Language Detector** : outil déterministe (langdetect ou fastText) — retire 30+ lignes du prompt, rend la règle infaillible
- **History Contextualized Query** : reformule la requête brute en question autonome et complète à partir de l'historique de conversation
- **Pedagogy Agent** : prompt épuré — débarrassé de la classification, des règles de langue, des garde-fous éthiques
- **CourseContext Tool (stub)** : renvoie `{{lesson_content}}` complet — comportement identique à aujourd'hui, placeholder pour le RAG du Lot 3
- **Tracing / observabilité** : branché dès ce lot (LangSmith ou Langfuse) — non négociable pour débugger un pipeline multi-étapes
- Pour les catégories E et G : fallback temporaire vers le Pedagogy Agent en attendant le Lot 5

**Valeur perçue :** indirecte — pas de changement visible pour l'apprenant, mais le prompt épuré améliore le suivi des instructions, et les refus prédéfinis ne consomment plus de LLM.

**Complexité :** moyenne — orchestrateur simple, pas de nouvelle techno.

**Risque principal :** régression comportementale si le découpage des prompts modifie des interactions subtiles → mitiger par exécution du dataset du Lot 1 avec les évaluateurs avant bascule.

---

#### Lot 3 — Infrastructure vectorielle + RAG simple non-itératif

**Objectif :** remplacer le CourseContext stub par une recherche ciblée dans le contenu des cours. Premier gain concret sur le coût tokens et la pertinence du contexte.

**Ce qui est implémenté :**
- **Indexation vectorielle** : pipeline d'ingestion des cours, choix du modèle d'embedding, stratégie de chunking (taille des chunks, overlap) — infrastructure à mettre en place avant de brancher le RAG
- **RAG Tool** : recherche top-k chunks dans la leçon courante uniquement — pas d'escalade, pas de boucle évaluateur à ce stade
- Remplacement du CourseContext stub par le RAG Tool dans l'orchestrateur — seul changement dans le pipeline, tous les autres agents restent identiques

**Valeur perçue :** forte — contexte ciblé injecté au Pedagogy Agent, réduction significative du coût tokens, réponses potentiellement plus précises sur les points pédagogiques clés.

**Complexité :** élevée — nécessite le choix et le déploiement d'un vector store (Qdrant, Weaviate, pgvector…), calibration du chunking et du top-k.

**Risque principal :** réponses moins complètes si le RAG rate des chunks pertinents — la stratégie de chunking et le top-k sont critiques à calibrer avant bascule.

---

#### Lot 4 — Query Intelligence avancée + RAG réflexif *(ReAct)*

**Objectif :** améliorer la qualité sur les questions complexes et les cas où la leçon courante ne suffit pas à répondre.

**Ce qui est implémenté :**
- **Query Rewriter / HyDE** : reformulation de la requête orientée retrieval — génère une réponse hypothétique et recherche par similarité avec elle pour maximiser la pertinence des chunks récupérés
- **Query Decomposer** : détecte les questions complexes, les fragmente en sous-questions atomiques pouvant être traitées indépendamment avec des sources différentes
- **Evaluator Agent** : juge la pertinence et la suffisance des chunks récupérés — déclenche une nouvelle passe de recherche si insuffisant
- **Escalade progressive** : leçon → thème → module → matière → sources externes (internet, MCP Studi) en dernier recours
- **Synthesis Agent** : agrège les réponses aux sous-questions en réponse finale cohérente

**Valeur perçue :** forte sur les questions pointues et les demandes multi-concepts — le système ne se limite plus au contenu de la leçon courante.

**Complexité :** élevée — boucle ReAct à borner strictement (max 2-3 itérations par passe), latence et coût à monitorer à chaque lot.

**Risque principal :** coût et latence augmentent avec chaque passe d'évaluation — l'Evaluator Agent doit être calibré pour éviter les boucles inutiles et les escalades trop fréquentes vers les sources externes.

---

#### Lot 5 — Exercise Agent *(horizon)*

**Objectif :** traiter proprement les catégories E (auto-évaluation) et G (quiz/exercice), actuellement en fallback temporaire sur le Pedagogy Agent depuis le Lot 2.

**Ce qui est implémenté :**
- **Exercise Agent** avec boucle ReAct légère : générer un exercice → évaluer sa difficulté par rapport au niveau de l'apprenant → ajuster si nécessaire
- Routing depuis le Guardrails & Intent Classifier vers l'Exercise Agent pour les catégories E et G

**Valeur perçue :** pédagogique — exercices mieux calibrés au niveau de l'apprenant, feedback plus pertinent.

**Complexité :** modérée — boucle simple, périmètre bien délimité, n'impacte pas le pipeline principal.

**Risque principal :** faible — un exercice imparfait est corrigeable sans régression sur le reste du système. C'est le lot le plus sûr pour expérimenter une boucle agentique libre.

---

## Livrables attendus en sortie d'atelier

- Liste des agents candidats **priorisés** par l'équipe
- Critères de choix **documentés**
- Prochaine session pour trancher et poser l'architecture
