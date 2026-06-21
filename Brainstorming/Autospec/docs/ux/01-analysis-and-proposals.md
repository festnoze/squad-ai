# Autospec UI/UX — Analyse critique & propositions d'évolution

> Branche `improve_UX`. Document d'entrée, soumis à 3 rounds de jugement / affinage
> avant la rédaction de l'architecture UX finale (`02-ux-architecture.md`).

## 0. Contexte & objectifs

Autospec orchestre une usine logicielle BMAD (PM → PO → Analyste → Architecte → QA →
Dev) qui transforme un besoin en code testé, par itérations, en parallèle sur
plusieurs *streams* (backend, frontend, …). Le frontend actuel (React + Vite, dark)
expose tout ça en temps réel via SSE.

Objectifs de la refonte demandés :

1. **Affichage plus adaptatif** (responsive, densité ajustable, place donnée à ce qui
   compte selon la phase).
2. **Interactions pendant le développement** : chat ciblé pour modifier un dev à venir
   *ou en cours* (story/tâche précise), et demandes d'ajout d'itérations / features à la
   volée.
3. **Visibilité de l'avancement du dev** : pour une US ou une tâche, montrer un
   **diagramme d'étapes** (analyse → contrats & tests-first → implémentation → QA →
   merge → done) plutôt qu'un simple badge de statut.

---

## 1. État des lieux (ce qui existe aujourd'hui)

### 1.1 Disposition générale

Layout **fixe** en 3 bandes verticales + une grille 2 colonnes :

```
Header (logo, provider/model, 📊 dashboard)
ProjectBar (sélecteur + chips de projets actifs + play/stop/archive/delete)
Workspace  ──────────────────────────────────────────────
  col-left (380px fixe)        │ col-right (1fr)
   • Chat (spec & feedback)    │  • WorkspaceViews : Board OU Iterations (flex 1.4)
   • Components (approbation)   │  • RunPanel (exécution + logs)       (flex 1)
   • Language                   │  • bouton CodeViewer
   • Backlog (lecture seule)    │
   • Architecture (lecture)     │
```

- **Board** : navigation par *drill-down* sur **4 niveaux** (Épics → Épic → Story →
  Tâche). Cartes avec barre de progression d'épic, badges (priorité, statut, qualité,
  mutation, couverture), critères d'acceptance dépliables (avec tests + Gherkin),
  sous-liste de tâches, filtres par stream.
- **RunPanel** : badge de phase, bandeaux (erreur, régression, **validation requise**,
  reprise auto), compteur coût/tokens, forecast, et une rangée de boutons
  (Lancer, Continuer, Retry, Stop app, Pause/Resume, Stop, menu ⋯ Livraison) + logs
  globaux repliables (cap 800 lignes).
- **Chat** : colonne gauche, messages par rôle (bordure colorée), envoi possible à tout
  moment ; carte brainstorming conditionnelle.
- **SSE** : 4 types d'évènements — `state` (snapshot complet), `log` (ligne + source),
  `notify` (toast), `deleted`.

### 1.2 Ce qui marche bien

- Temps réel sans polling, reconnexion + replay (`Last-Event-ID`).
- Système de badges riche (statut, qualité, mutation, couverture, dépendances, blocked-by,
  merge).
- Multi-stream (badges + filtre).
- Chat multi-rôles intégré (pm/po/dev/analyste/architecte/qa/critique/juge).
- Tokens de design centralisés (`:root` variables), `prefers-reduced-motion` respecté.

---

## 2. Critique (problèmes identifiés)

### 2.1 Disposition & adaptativité

- **Layout non responsive** : `grid-template-columns: 380px 1fr`, aucune media query.
  Sous ~1200px la colonne gauche écrase le Board ; sur écran large la sidebar de 380px
  est disproportionnée et la place perdue ne profite pas au contenu utile.
- **Ratio Board/RunPanel arbitraire** (1.4 / 1) et non ajustable par l'utilisateur ; les
  logs volent de la place au Board, ou inversement.
- **Colonne gauche = pile hétérogène** (chat + components + language + backlog +
  architecture) : 5 panneaux empilés, beaucoup conditionnels, sans hiérarchie claire de
  ce qui est pertinent *maintenant* (selon la phase).
- **Densité non réglable** : textes 10–13px, badges qui débordent en ligne sur une story
  (priorité + statut + qualité + mutation + couverture).

### 2.2 Visibilité de l'avancement (le point central)

- **Aucune granularité sous le statut** : `in_progress` ne dit pas si l'item est en
  analyse, en écriture des tests (red), en implémentation, en QA (couverture/mutation/
  refine) ou en merge. L'utilisateur voit « en cours depuis 2 min » sans savoir *où*.
- **Le backend connaît pourtant ces étapes** (séquence réelle de `_abuild_work_item` :
  `_adesign_tests` → dev red → dev green → vérif pytest → couverture/refine/mutation →
  commit/merge) **mais ne les expose pas** : pas de champ `stage`, pas d'évènement
  `stage`. La seule trace est dans les logs (`source = dev:US-3`, `qa:US-3`).
- **Tâches plus pauvres que les stories** : pas de `test_plan`, ni qualité/mutation/
  couverture ; statut seul.
- **Logs non corrélés** : un mur de texte global, non filtrable par story/tâche/source ;
  difficile de retrouver l'erreur d'un item précis.
- **Pas de capacité / ETA** : aucun « 3 en cours, 5 en file, 12 faits », pas de vélocité,
  pas d'estimation de fin.

### 2.3 Interactions pendant le dev

- **Chat projet-global uniquement** : un message pendant le build alimente
  `build_guidance[]` partagé à **tous** les agents dev — impossible de cibler une story/
  tâche précise (« pour US-4, utilise un cache »).
- **Modifs d'item ambiguës** : éditer la description d'une story en cours ne dit pas si
  ça s'applique à l'itération courante, aux tâches en vol, ni si les tests sont rejoués.
- **Ajout de feature/itération lent** : passe par l'analyste (`_aimpact_analysis` via chat
  en phase dormante) ; pas de voie rapide « injecter cette story dans le prochain batch ».
- **Actions cachées** : menu ⋯ Livraison, bandeau d'**approbation** (dans l'entête du
  RunPanel, facile à rater), CodeViewer discret.
- **Confusion Pause / Stop / Stop app** sans explication.

### 2.4 Divers

- Backlog & components quasi en lecture seule (pas d'édition/priorisation depuis l'UI).
- Pas de virtualisation (DOM lourd sur gros projets).
- Pas de métadonnée projet dans l'entête (on perd le fil avec plusieurs onglets).

---

## 3. Propositions d'évolution

Les propositions sont regroupées par thème, avec un identifiant (`P#`) pour le scoring.

### 3.1 Disposition adaptative

- **P1 — Shell responsive à 3 zones réglables.** Remplacer la grille fixe par un layout
  fluide : **rail de navigation** (gauche, collapsible en icônes), **scène centrale**
  (le focus courant), **panneau contextuel** (droite, dock). Breakpoints :
  - ≥1600px : 3 colonnes.
  - 1100–1600px : 2 colonnes (contextuel en *drawer* à la demande).
  - <1100px : 1 colonne, navigation par onglets bas/haut.
- **P2 — Disposition pilotée par la phase (« phase-adaptive »).** La scène centrale et le
  panneau contextuel changent de contenu selon `phase` :
  - *spec* → chat plein cadre (interview), reste réduit.
  - *plan/architect* → backlog + plan + architecture mis en avant.
  - *build* → Board + flux d'activité + progression au centre.
  - *done* → revue d'itération, livraison, métriques.
- **P3 — Splitters draggables + densité.** Poignées de redimensionnement persistées
  (localStorage) ; sélecteur de densité (Confort / Compact) ; thème clair en option.
- **P4 — En-tête de projet contextuel** : nom, phase, itération, coût/budget, ETA, toujours
  visibles ; chips de projets actifs déplacés dans le rail.

### 3.2 Visibilité de l'avancement

- **P5 — Diagramme d'étapes par item (« stage tracker »).** Pour chaque US/tâche en cours,
  un *stepper* horizontal :
  `Analyse → Contrats & tests (red) → Implémentation (green) → QA → Merge → Done`,
  avec état par étape (à venir / en cours animé / faite / échec), durée écoulée, et
  l'étape échouée surlignée. Variante compacte (mini-pastilles) en vue liste, détaillée en
  vue item.
  - *Backend requis* : ajout d'un enum `BuildStage` + `current_stage`/`stage_started_at`
    sur `UserStory` et `Task` ; transitions posées dans `_abuild_work_item` ; nouvel
    évènement SSE `stage` (item_id, stage, ts) pour mise à jour fine sans resync complet.
- **P6 — Vue « Activité » live** : timeline des items en cours (qui est à quelle étape,
  depuis combien de temps), avec capacité (`max_parallel_devs`) et file d'attente
  (ready / blocked-by). Remplace la lecture des logs pour suivre le build.
- **P7 — Logs corrélés** : filtrage par item/stream/source, et depuis un item, « voir ses
  logs » (filtre `source = dev:US-3 / qa:US-3`). Marqueurs de régression/erreur cliquables.
- **P8 — Capacité & ETA** : bandeau « N en cours · M en file · K faits · ~ETA », vélocité
  par itération (réutilise `iteration_usage` + forecast existant).
- **P9 — Board en swimlanes par stream (option build).** Pendant le build, vue colonnes
  par étape (Kanban : To do / Analyse / Tests / Dev / QA / Merge / Done) **ou** lanes par
  stream, en complément du drill-down hiérarchique (qui reste pour l'exploration).

### 3.3 Interactions pendant le dev

- **P10 — Chat contextuel ciblé** : depuis une story/tâche, un fil de chat dédié qui écrit
  une consigne *scopée* à cet item.
  - *Backend requis* : `story.guidance[]` / `task.guidance[]` + endpoints
    `POST /stories/{id}/chat` et `/tasks/{id}/chat` ; injection dans le prompt dev de cet
    item uniquement. Le chat global reste pour le feedback transverse.
- **P11 — Composeur d'intention unifié** : une barre d'action (type « palette ») où l'on
  tape une demande et choisit la **cible** (projet / itération / épic / story / tâche) et
  le **type** (consigne dev, modifier critères, ajouter story, ajouter itération). Route
  vers le bon endpoint.
- **P12 — Injection rapide de feature/story** : `POST /inject-feature` (scaffold direct
  dans le batch *ready*, sans attendre l'analyste) ; et `POST /stories/{id}/extend` pour
  ajouter des critères à une story encore `todo`.
- **P13 — Modale d'approbation proéminente** : quand `awaiting_approval`, surfaçage clair
  (bandeau scène + toast + focus), montrant *quoi* est à valider, avec Approuver/Rejeter.
- **P14 — Actions item explicites & cohérentes** : regrouper Relancer/Forcer/Rejouer/Diff/
  Voir logs/Chat ciblé dans un menu d'item homogène ; clarifier Pause vs Stop vs Stop-app
  (libellés + tooltips).

### 3.4 Cohérence & système

- **P15 — Système de design étendu** : tokens (espacements, rayons, ombres, couleurs de
  statut/étape), composants réutilisables (Badge, Stepper, Card, Drawer, Toolbar),
  thèmes clair/sombre, densités.
- **P16 — Édition du backlog & des composants** depuis l'UI (priorisation, ajout
  d'hypothèses, édition de rationale) — transforme les panneaux « lecture seule » en outils.
- **P17 — Virtualisation** des listes (stories/logs) pour les gros projets.

---

## 4. Changements backend induits (synthèse)

| Besoin UX | Changement backend | Ancrage |
| --- | --- | --- |
| P5/P6 stage tracker | `BuildStage` enum + `current_stage`,`stage_started_at` sur `UserStory`/`Task` ; `_set_stage()` ; évènement SSE `stage` | `models.py`, `orchestrator/pipeline.py` (`_abuild_work_item`), `orchestrator/events.py` |
| P10 chat ciblé | `guidance[]` sur `UserStory`/`Task` ; `POST /stories/{id}/chat`, `/tasks/{id}/chat` ; injection prompt par item | `models.py`, `api/server.py`, `agents/prompts.py`, `pipeline.py` |
| P12 injection rapide | `POST /inject-feature`, `POST /stories/{id}/extend` | `api/server.py`, `pipeline.py` (`aadd_story`) |
| P7 logs corrélés | (déjà : `source` taggé par item) — exposer/filtrer côté UI ; éventuellement endpoint logs filtrés | UI surtout |
| P8 ETA/capacité | réutiliser `forecast` + `iteration_usage` ; exposer file ready/blocked du work-graph | `streams.py`, `api/server.py` |

Principe : **changements backend minimaux et additifs** (nouveaux champs avec défauts,
nouveaux endpoints, nouvel évènement) — aucune rupture de l'existant.

---

## 5. Risques & contraintes

- **Build en worktrees** : un item se construit dans un git worktree isolé ; les
  transitions de `stage` doivent être posées dans le worker et propagées via `_sync()`/
  évènement, pas via le système de fichiers.
- **Compat état persistant** : tout nouveau champ doit avoir un défaut (états anciens
  chargés sans casse — cf. migrations Pydantic existantes).
- **Volume d'évènements** : préférer un évènement `stage` léger à des resync `state`
  complets pour les transitions fréquentes.
- **Frontend lui-même généré par Autospec** : la refonte concerne l'**UI d'Autospec**
  (`Autospec/frontend`), pas le frontend des produits générés.

---

## 6. Critères de réussite

1. On comprend en un coup d'œil *où en est* chaque item (étape, durée, blocage).
2. On peut adresser une consigne à **une** story/tâche, et ajouter une story/itération
   sans attendre, pendant le build.
3. Le layout reste lisible de ~1024px à 4K, avec densité réglable.
4. Aucune régression backend ; changements additifs couverts par tests.
5. Un parcours e2e Playwright valide : suivi d'avancement, chat ciblé, ajout de feature.
