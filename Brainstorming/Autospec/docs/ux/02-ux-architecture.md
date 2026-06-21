# Autospec UI/UX — Architecture cible (synthèse retenue)

> Issu de `01-analysis-and-proposals.md` + 3 rounds de jugement/affinage/exploration
> (workflow `ux-judge-refine-loop`, 19 agents). Ce document fixe la vision retenue
> **et** le périmètre d'implémentation MVP (additif, testable) vs ce qui est différé.

## 1. Vision — « Mission control » d'une équipe BMAD autonome et auto-réparante

Une seule phrase guide toutes les surfaces : **on regarde un pipeline d'étapes
s'exécuter en parallèle (worktrees git), on voit d'un coup d'œil quel item est
*bloqué / lent / en échec / en auto-réparation*, et on peut intervenir sur un agent,
une étape ou un stream sans arrêter tout le run.**

- **Métaphore héros = le PIPELINE d'étapes** : `Analyse → Tests (red) → Implémentation
  (green) → QA → Attente merge → Merge → Done`.
- L'**équipe** (pm/architecte/dev/qa/critique/juge) est une **lentille** sur ce pipeline,
  pas une surface concurrente.
- Le comportement distinctif aujourd'hui caché — l'**auto-réparation** (refine
  critique/juge, restauration snapshot, re-run régression/mutation) — devient un récit
  **de premier plan** sur le stepper : on voit enfin que l'usine se répare.

Les 4 vues concurrentes d'aujourd'hui (Board hiérarchique, Iterations, RunPanel, logs)
convergent vers **une surface canonique « Activité »** alimentée par le work-graph ; tout
le reste y devient un rôle : compteurs = en-tête, kanban = bascule de la même donnée,
steppers = lignes, équipe = filtre, logs/décisions/recovery = tiroir d'item.

## 2. Idées retenues (must / should / could) et abandonnées

**MUST** — P5 stage tracker (+recovery, lent/bloqué), P5b heartbeat tick, P6 Activité
canonique, P13 approbation (bannière unique + payload enrichi + échelle d'attention),
P14 menu d'item canonique + cancel-in-flight, P10 chat ciblé par item, N4 stamp
`current_persona`.

**SHOULD** — P12 revise-scope-then-retry + inject/extend, P8 bande débit + coût/item +
pause par stream, P4 en-tête persistant coût/budget/ETA, P1 shell responsive, P3 densité
+ splitter, P15 design system (canaux orthogonaux), N4.

**COULD** — N11 carte de couverture de la spec, N13 carte « bon retour » (recap), N12
fleet glance multi-projets, N15 dry-run de conséquence avant action destructive.

**DROP** — thème clair (coût élevé / valeur faible sur CSS mono-palette 2554 lignes),
P16 backlog éditable (couvert par P12), P17 virtualisation (fast-follow), N2 scrubber
timeline, N10 heatmap fichiers, N3/N8 rubans d'anomalie (couverts par médiane+recovery),
N5 page partageable, N7 ledger/undo (préférer N15 prévention), N14 handoff trails, N9
autonomy dial (fast-follow).

## 3. Architecture des surfaces

### 3.1 Shell adaptatif (P1/P3)
- Grille CSS pilotée par tokens sur `.workspace` : `--rail-w / --scene-w / --dock-w`
  (remplace le `380px 1fr` fixe). 3 breakpoints : ≥1600 (3 cols), 1100–1600 (2 cols, dock
  en *drawer*), <1100 (1 col, onglets). **Axes responsive et densité couplés** : sous
  1200px → `data-density=compact` + dock en drawer.
- Densité mesurable : deltas de tokens (`--font-sm 13→12`, `--row-pad 8→4`, badges
  réduits à priorité+statut avec popover `+N`, critères repliés par défaut). Splitter qui
  écrit les largeurs en `localStorage`.
- **Rail** : fleet strip (N12) + nav projet. **Scène** : contenu *phase-adaptive*
  (carte d'élicitation spec → Activité en build → résumé en done). **Dock** : tiroir d'item.
- Livré derrière un flag **par session** `data-shell=v2` (réversible) ; audit overflow
  Board/RunPanel à chaque breakpoint avant activation par défaut.

### 3.2 Avancement — Activité canonique (P5/P6/N4)
- **Une vue Activité** alimentée par `build_work_graph` / `ready_items` / `blocked_by`
  (déjà dans `streams.py`). En-tête à 60% : `N en cours · M en file · K faits` +
  `stall_reason` (« pourquoi rien ne bouge ») + **chip persistant échecs/bloqués** qui
  survit au scroll et à la bascule kanban.
- **Lignes = steppers** par item. Le stepper encode d'un coup d'œil :
  - **position** (étape faite/active),
  - **échec** (anneau rouge, token le plus contrasté, seul `pulse` réservé),
  - **lent** (ambre « long » si écoulé > médiane glissante × 1.5, fallback statique au début),
  - **anneau de blocage** (`merge_wait` détenteur / `awaiting_approval` / `budget_paused`
    / `at_parallel_cap`, depuis work-graph + propriétaire de `_merge_lock`),
  - **auto-réparation comme état** : `✓ green · refine 2/3 ▸` (distinct de « terminé en
    échec »).
- **Région « à traiter » épinglée** : remonte les lignes failed/blocked/awaiting-approval.
- **Ordre déterministe de collapse des badges** : `blocked/failed > approval > stepper >
  persona > elapsed` ; qualité/couverture/mutation/priorité passent d'abord dans un
  popover `+N`.
- **Delta « changé dans les N dernières min »** (diff client entre ticks) : repère les
  lignes qui ont avancé / nouvellement échoué / atteint `merge_wait`.
- **Dot de fraîcheur** : grise la pastille si le tick > 25 s (jamais « bloqué » lu comme
  live avant d'agir).
- **Crew = rail de filtre** dans Activité (actif/inactif/bloqué + sur quel item + écoulé ;
  clic persona → filtre lignes + logs via tags `dev:US-3` / `qa:US-3`).
- Clic sur une pastille d'étape → **tiroir d'item** : stepper complet, sous-ligne recovery
  narrant l'auto-réparation avec la raison de l'agent, et **logs filtrés** de cet
  item+étape.

### 3.3 Interaction pendant le build (P10/P12/P13/P14/N15)
- **Un modèle d'action, deux entrées** : menu d'item canonique
  (`Retry / Force / Replay / Diff / Logs / Chat / Cancel-in-flight`) + palette `Cmd-K` qui
  route vers ces mêmes verbes avec **chip de cible obligatoire**, confirm destructif et
  raccourci « aller au prochain échec ».
- **Chat ciblé par item** : `guidance: list[GuidanceEntry]` sur `UserStory`/`Task`,
  endpoints `POST /stories|tasks/{id}/chat`, injecté dans le prompt dev de cet item ; état
  de livraison par entrée (`queued / applied / too_late`). Si `too_late` → « Mettre en
  file prochaine itération » ou « Relancer maintenant avec la consigne » (echo
  « consigne G ré-injectée dans le prompt dev de US-4 (itération N) »).
- **Ajouter feature/itération** : « Revise scope » (édite critères/desc d'un item en
  échec → applique au retry via `editStory`+retry) ; inject/extend créent en `todo` avec
  **aperçu d'impact** une ligne (« dépend de US-3 (en QA) ; planifié après »).
- **Dry-run de conséquence (N15)** avant toute action destructive/scope (force-done →
  « débloque US-5, US-7 ; saute 2 critères non couverts »).
- **Idempotence** : chat/inject/cancel/retry/force contournent le `fetchIdempotent`
  auto-retry (api.ts:26) ou portent une clé d'idempotence ; le blind-upsert (App.tsx:145)
  est remplacé par un merge de tableaux par id (statut serveur gagne, optimiste préservé).
- **Cancel-in-flight honnête** : token d'annulation par item vérifié entre étapes,
  **refusé pendant le merge** (`_merge_lock` détenu), teardown propre du worktree avant
  retour à `todo`. *(Voir périmètre §5 — différé au-delà du MVP.)*

### 3.4 Approbation (P13)
- **Bannière unique** = surface primaire ; pastille d'étape et en-tête = reflets passifs.
- `awaiting_approval` (string aujourd'hui) **enrichi** d'une référence d'artefact (diff/
  résumé spec/archi) → la bannière montre *quoi* approuver.
- **Échelle d'attention unique** (`approval > stall > anomaly > milestone`) dans la couche
  tokens (P15) ; seuls approval + échec terminal peuvent lever une notif OS.

### 3.5 Design system (P15)
- Canaux **orthogonaux** : `couleur = état d'étape`, `forme/icône = persona`,
  `position = ordre de file`, `motion(pulse) = attention seule`. Échelle de statut/étape
  *colorblind-safe* plafonnée. Le token le plus contrasté + le seul pulse réservés à
  failed/blocked/needs-attention. Qualité/couverture/mutation/priorité **démotés** au
  popover `+N` (pas de couleur au repos).

## 4. Changements backend (additifs, défauts sûrs)

| # | Changement | Fichiers |
| --- | --- | --- |
| B1 | `BuildStage` enum ; `current_stage`, `stage_started_at`, `current_persona`, `recovery:{attempt,max_attempts,kind}` sur `UserStory`/`Task` | `models.py` |
| B2 | Stamper B1 aux transitions réelles de `_abuild_work_item` / `_arun_item_dev` / `_adesign_tests` + sites refine/régression/mutation/merge | `orchestrator/pipeline.py` |
| B3 | `guidance: list[GuidanceEntry]` sur `UserStory`/`Task` ; injection dans le prompt dev par item | `models.py`, `agents/prompts.py`, `pipeline.py` |
| B4 | Endpoints `POST /stories/{id}/chat`, `POST /tasks/{id}/chat`, `POST /stories/{id}/extend` (clé d'idempotence) | `api/server.py`, `pipeline.py` |
| B5 | 5e WsEvent `tick` (~10 s en BUILD) : `{project_id, items:[{id,current_stage,stage_started_at,recovery,current_persona}], counts, stall_reason, ts}` ; démarré à l'entrée BUILD, annulé à stop/dispose/archive ; non rejoué via Last-Event-ID | `orchestrator/events.py`, `pipeline.py`, `api/server.py` |
| B6 | Owner-tracking de `_merge_lock` → `stall_reason` + anneau de blocage | `pipeline.py` |
| B7 | Exposer un résumé work-graph (`ready[]`/`blocked_by{}`/`in_flight[]`) sur le snapshot | `streams.py`, `pipeline.py` |
| B8 *(should)* | `item.cost_usd` (accumulé aux sites LLM) ; `awaiting_approval` enrichi ; pause par stream ; `last_decision` | `models.py`, `pipeline.py`, `agents/*` |
| B9 *(diff)* | Cancel-in-flight (token + teardown worktree + refus pendant merge) | `pipeline.py` |

Principe : **tout champ a un défaut** (états persistés anciens chargés sans casse).

## 5. Périmètre d'implémentation (cette branche)

Contrainte forte : il existe une suite **e2e Playwright exhaustive** + ~47 fichiers de
tests backend + tests vitest (App/Board/WorkspaceViews/RunPanel/ProjectBar). La refonte
est donc **additive** : on ajoute les nouvelles surfaces sans casser l'existant, puis on
bascule par défaut.

### MVP livré (objectifs cœur, testés)
1. **Backend** B1, B2 (stamp dans le chemin réel, donc aussi en démo fake-agents), B3,
   B4, B5, N4 (`current_persona`), B6 (owner `_merge_lock` → `stall_reason`). Tests
   backend additifs.
2. **Frontend** :
   - Tokens design + **shell adaptatif** (grille par tokens + breakpoints + densité).
   - `work.ts` étendu (helpers d'étape) + **composant `Stepper`** + **vue `Activity`**
     ajoutée comme onglet de `WorkspaceViews` (Board conservé), avec en-tête compteurs +
     chip échecs + région à-traiter + filtre crew.
   - **Chat ciblé par item** + menu d'actions d'item (réutilise endpoints existants + B4).
   - **Bannière d'approbation** améliorée.
   - Gestion du `tick` (types.ts/api.ts/App.tsx).
   - Tests vitest des nouveaux composants ; suite existante maintenue verte.
3. **E2E** : nouveau scénario Playwright (mode fake-agents) couvrant : suivi du stage
   tracker, chat ciblé d'une story, ajout/extend d'une feature ; suite e2e existante
   maintenue.

### Différé (documenté, fast-follow)
- B9 **cancel-in-flight** (teardown worktree mid-build) — risque de deadlock `_merge_lock`,
  à valider sous parallélisme réel ; livré comme « demande d'annulation » sûre seulement.
- Collapse complet « 4 vues → 1 » et suppression du Board (Activity d'abord additif,
  défaut en phase build).
- B8 coût/item, pause par stream, `last_decision` enrichi ; N11/N12/N13/N15 ; P15 complet ;
  virtualisation (P17) ; thème clair (abandonné).

## 6. Risques (rappel synthèse)
- Cancel-in-flight = pièce la plus dure (orphelin `_merge_lock`) → différé/sécurisé.
- `current_persona` / owner `_merge_lock` / coût-item : si l'un est faux, l'intervention
  cible le mauvais agent → pire que pas de signal.
- Inflation du snapshot full → le tick borne la churn mais surveiller la taille.
- Migration de tests réelle (nouveaux champs + 5e WsEvent) → planifiée, additive.
- Le tick borne la staleness à ~10 s → le grey-out de fraîcheur doit être livré **avec** le tick.
