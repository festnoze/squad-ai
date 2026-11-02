# Autospec v2 : plan de refonte

Version 0.1, 2 novembre 2026. Document de travail à challenger avant toute ligne de code.

Ce plan répond à un constat : Autospec n'arrive plus à terminer une itération, même sur un
projet trivial, alors que le harness qu'il enveloppe (Claude Code, Codex) termine le même
projet seul en quelques minutes. Il ne propose ni de repartir de zéro, ni d'ajouter une
vague corrective de plus. Il propose d'inverser la charge de la preuve : un noyau minimal,
mesuré sur un banc fixe, et chaque mécanisme historique ne revient que s'il bat la mesure.

Trois livrables sont décrits ici : le périmètre du noyau v2 (section 4), le banc de mesure
(section 5) et la liste garder / jeter / réévaluer (section 6). Les sections 1 à 3 posent
les faits et les principes ; les sections 7 à 9 donnent le séquencement, la méthode de
travail et les questions ouvertes.

## 0. Résumé

- Le code généré par l'usine est globalement correct ; ce sont l'orchestration et la
  plomberie d'exécution qui échouent, coûtent et bloquent.
- Le noyau v2 est un pipeline séquentiel sans drapeau : brief, plan, puis une story à la
  fois (plan de tests QA, agent dev en TDD avec ses outils natifs dans un espace confiné,
  vérification indépendante par l'usine en environnement propre), smoke, rapport.
- L'agent dev redevient un agent : il lit, écrit, lance les tests lui-même. L'usine ne
  refait pas son travail ; elle le contrôle (environnement propre, tests QA intouchés,
  traçabilité critères / tests, smoke).
- Un banc de cinq projets et six métriques est posé AVANT le noyau, et joué sur trois
  configurations : v1 actuelle, Claude Code nu, v2. Rien n'est mergé sans mesure.
- Cible de taille : noyau v2 sous 2 500 lignes, prompts sous 400, configuration sous 15
  réglages. Tout le reste de v1 est gelé sur une branche d'archive.

## 1. Point de départ : faits mesurés le 2 novembre 2026

| Mesure | Valeur | Source |
|---|---|---|
| Backend `autospec/` | 50 261 lignes Python (25 000 en septembre) | `wc -l` |
| `orchestrator/pipeline.py` | 11 685 lignes, une classe `Pipeline`, ~320 méthodes | idem |
| Réglages dans `config.py` | 167 champs, `.env` de 380 lignes en 9 sections | idem |
| Tests backend | 2 229 fonctions, 226 fichiers, 45 700 lignes ; 30 à 66 min par passe | `grep`, journal REM-24 |
| Drapeaux épinglés par `tests/conftest.py` | ~50, la plupart à l'inverse de la production | `conftest.py` l. 31-178 |
| Dernier run « réussi » (22 sept.) | Counter webapp : 3 stories vertes, 117 tests verts, mais `timed_out` à 2 h, 40 appels, 46,88 $ | `build-logs/p3/summary.json` |
| Campagne Relais Support (8 oct.) | 27 tâches « done » en 116 min, 21,81 $ ; verdict indépendant 27 FAIL / 17 PASS / 13 NOT_VERIFIED sur 57 critères | `docs/validation/support-client/03_plan_remediation_autospec.md` §1 |
| Programme de remédiation (9-16 oct.) | REM-00 à REM-25, 272 commits en 5 jours, +25 000 lignes, ~100 fichiers de preuves | `git log`, `artifacts/remediation/` |
| Relance après remédiation (REM-25, 12 oct.) | Plan rejeté par les nouvelles gates, 0 PASS, aucun code métier livré ; programme « non clos » | même plan, tableau §3 et journal §7 |
| État de `main` | Venv non synchronisé au 2 nov. (`argon2` absent, 8 erreurs de collecte) ; après `uv sync --frozen` : 3 567 PASS / 3 FAIL / 108 SKIP en 20 min (2 échecs liés à une coupure DNS passagère) | run du 2 nov., commit `5dea3e71` taggé `v1-ref` |
| Mode d'exécution de l'agent dev depuis le 11 oct. | `claude -p --tools "" --disallowedTools "*" --restricted --safe-mode` : aucun outil natif, fichiers entiers écrits via un protocole JSON, tests lancés uniquement par l'usine, 8 tours médiés × 2 tentatives | `agents/runner.py` l. 725-880, `agents/file_broker.py` |
| Documentation | 15 documents racine + 4 dans `docs/validation` + ~100 preuves ; aucun ne décrit l'état réel, six compteurs de tests différents | dépouillement du 5 oct. |

Deux faits dominent. Le premier : l'usine a produit du code vert à plusieurs reprises
(Counter webapp, Todo CLI, biblio) ; ce n'est pas la génération qui manque. Le second : la
seule réponse apportée à chaque échec a été d'ajouter un mécanisme et un drapeau, jamais de
retirer. La campagne d'octobre est l'aboutissement de cette logique : la fabrique la plus
contrôlée jamais produite ne livre plus rien du tout.

## 2. Diagnostic : pourquoi une itération ne se termine pas

### C1. L'agent dev est aveugle

Depuis le 11 octobre, l'agent dev n'a aucun outil. Il reçoit un prompt, répond par un JSON
`write_files` avec des fichiers entiers, et ne saura si ses tests passent qu'à la tentative
suivante, si l'usine lui renvoie la sortie pytest. Le cycle rouge / vert / refactor, qui est
toute la valeur de l'approche TDD, est physiquement impossible : l'agent écrit les tests et
le code dans le même tour sans jamais les exécuter. Avec `DEV_MAX_ATTEMPTS=2` et
`PROVIDER_TOOL_ROUNDS=8`, une story dispose de deux essais à l'aveugle.

Ce choix répond à un incident réel (campagne du 8 octobre : un agent de réparation a lancé
un arrêt global des processus Python de l'hôte, tuant l'usine). La contrainte de confinement
est légitime. La réponse (retirer les outils) est la mauvaise : elle confine en rendant
l'agent inutile. La v2 confine l'exécution, pas l'agent (section 4.3).

### C2. La plomberie d'exécution a remplacé la méthode

Les post-mortems de juillet à octobre (messagerie2 : 41 h, 11 verdicts canari sur 11 faux
positifs ; recettes : 13 défauts ; Counter : évaluateur gelé 45 min par un petit-fils
uvicorn ; Relais : collision `clock.py`/`errors.py`, dépendance Argon2 installée hors
manifest) décrivent presque exclusivement des défaillances d'infrastructure que l'usine a
choisi de porter elle-même : worktrees git, merges, canari post-merge, jonctions
`node_modules`, venv détruites, kill d'arbres de processus Windows, ports occupés.

Les mécanismes corrigent des mécanismes : les streams parallèles créent des conflits de
merge, le canari les détecte, le canari a des faux positifs, d'où la rafale et le replay,
d'où la contention, d'où le mode solo, le budget de requeue, la libération de slot et le
bonus de fan-out. Six mécanismes pour stabiliser un parallélisme plafonné à
`MAX_PARALLEL_DEVS=2`, c'est-à-dire un gain théorique de 2 au prix de la majorité des
défauts documentés.

### C3. Rien n'a jamais été mesuré

Le run de référence KPI (W0.6 du Verified Swarm) n'a jamais été archivé ; la vague 4
« validation » de `NEXT_STEPS_2026-09.md` n'a jamais été exécutée ; la règle affichée
« une vague qui ne bouge pas sa métrique est revertée » n'a jamais été appliquée. La suite
de tests, verte ou non, valide une configuration que la production ne joue pas (conftest).
Chaque vague a donc été livrée sur la foi de tests unitaires, puis découverte défaillante au
run supervisé suivant, à 20-60 $ le run.

### C4. Le monolithe et les drapeaux comme architecture

Une classe de 11 700 lignes et 167 réglages ne se raisonnent pas. Les interactions entre
drapeaux (2^100 combinaisons, cinq ou six jouées) sont la source des régressions
« inexplicables ». L'usine impose à ses agents une architecture 3 couches et des unités de
3 fichiers, et ne s'applique ni l'une ni l'autre.

### C5. La remédiation d'octobre a aggravé C1 à C4

Le programme REM a ajouté 25 000 lignes, un paquet `validation/` de 8 000 lignes, des
contrats d'acceptance scellés par hash, des revues de sources par GPT, des « reçus » de coût
immuables. Ses principes sont souvent justes (dépendances déclarées dans le manifest,
vérification en environnement propre, tests QA intouchables, oracle hors du produit). Son
exécution a été une nouvelle couche de mécanismes sur le monolithe, par des agents en
parallèle sous verrou de fichiers, sans jamais rejouer la production : résultat 0 PASS.

## 3. Principes de la v2

P1. **Le harness exécute, l'usine dirige.** L'agent dev est une session Claude Code (ou
Codex) avec ses outils natifs, dans un espace de travail confiné. L'usine fournit la
méthode (story, critères, plan de tests, règles) et contrôle le résultat. Elle ne
ré-implémente ni boucle d'outils, ni gestion de contexte, ni retry interne du harness.

P2. **Séquentiel d'abord.** Une story à la fois, dans le seul dépôt du projet, sans
worktree, sans merge, sans canari. Le parallélisme est un candidat de la phase 4 (section
7), admis seulement s'il bat la mesure.

P3. **Zéro drapeau fonctionnel.** Un mécanisme existe ou n'existe pas. La configuration se
limite au fournisseur, au modèle, aux chemins, aux budgets et aux timeouts (cible : moins
de 15 réglages). Pas de « 0 = comportement historique ».

P4. **L'usine vérifie, elle ne croit pas.** Après chaque story : suite complète rejouée par
l'usine dans un environnement reconstruit depuis manifest + lock, tests QA comparés à leur
empreinte, traçabilité critère / test exigée, smoke du produit. Ce sont les quatre
contrôles conservés de v1 et d'octobre.

P5. **Chaque incrément passe le banc.** Un incrément du noyau (ou un mécanisme réintroduit)
est mergé si et seulement si le banc (section 5) ne régresse pas. La suite unitaire du
noyau reste sous 30 secondes ; la mesure réelle est le banc.

P6. **Un seul document d'état.** `docs/REFONTE_V2.md` (ce plan) puis `docs/STATE.md` ;
tout le reste part en `docs/archive/` en phase 5.

P7. **Un seul rédacteur pour le noyau.** Le noyau v2 se construit en sessions séquentielles,
un incrément par session, jamais par essaim d'agents sous verrou de fichiers (la méthode
d'octobre).

## 4. Périmètre du noyau v2

### 4.1 Pipeline et machine à états

```
CRÉÉ
  └─ BRIEF        PM : interview (chat) ou brief fourni. Sortie : brief.md
  └─ PLAN         PO : epics, stories, critères d'acceptance identifiés (US-x.AC-y),
                  Gherkin, depends_on, priorité. Sortie : plan.json + features/*.feature
  └─ BUILD        pour chaque story dans l'ordre topologique puis priorité :
       ├─ QA      plan de tests par critère (nodeids attendus, couche, mocks)
       ├─ DEV     agent natif : tests rouges, implémentation, suite verte (≤ N tentatives)
       └─ VERIFY  usine : env propre, suite complète, empreinte tests QA, traçabilité AC
  └─ DELIVER      smoke (import / --help / HTTP 200 selon profil), commit « story done »
  └─ DONE | NEEDS_ATTENTION | STOPPED | ERROR
```

États d'une story : `todo`, `in_progress`, `done`, `failed`. Rien d'autre (plus de `red`,
`green`, `merge_wait`, `merging`, `solo`...). Une story `failed` après N tentatives arrête
l'itération en `NEEDS_ATTENTION` avec la sortie de la dernière vérification ; l'humain
relance, édite la story ou force.

Transitions explicites dans un module `core/machine.py` testé à 100 % avec un `FakeRunner`.
Toute transition émet un événement SSE (réutilisation de `orchestrator/events.py`).

### 4.2 Contrat de l'agent dev

Entrée (prompt, moins de 2 000 caractères hors story) :
- la story, ses critères identifiés, son Gherkin, le plan de tests QA ;
- les règles : écrire d'abord les tests du plan QA (rouges), implémenter, lancer la suite
  jusqu'au vert, ne jamais modifier un test QA existant, déclarer toute dépendance dans le
  manifest, marquer chaque test `# AC: US-x.AC-y` ;
- la structure attendue du dépôt (scaffold existant) ;
- rien d'autre. Pas de catalogue de skills, pas de bloc architecture, pas de leçons, pas de
  contrats de dépendances, pas de consignes d'octobre. Chaque ajout au prompt est un
  candidat de phase 4, mesuré.

Sortie : un JSON final `{summary, tests: [{ac_id, nodeids}], dependencies_added}`.

L'agent dispose de Read, Edit, Write, Glob, Grep et d'un Bash restreint aux commandes de
test et de build du projet (`uv run pytest`, `npm test`, `npm run build`, `uv sync`,
`npm ci`). Il tourne avec `cwd` = espace de travail du projet, `--max-turns` borné,
`--max-budget-usd` borné, `--output-format json`.

### 4.3 Confinement

Le besoin né de l'incident du 8 octobre est conservé ; la solution change. Deux options,
tranchées par le spike de la phase 0 :

- **Option A (visée) : Claude Code dans un conteneur.** Image `autospec-agent` (claude CLI,
  uv, node, git), espace de travail monté en volume, réseau limité au fournisseur et aux
  registres de paquets, pas d'accès au système hôte. L'agent a tous ses outils, l'hôte est
  hors d'atteinte. Prérequis : Docker Desktop dans la bonne session Windows (piège connu).
- **Option B (repli) : hôte + liste blanche.** `--allowedTools` restreint (`Read`, `Edit`,
  `Write`, `Glob`, `Grep`, `Bash(uv run pytest*)`, `Bash(npm test*)`, `Bash(npm run build*)`),
  `--add-dir` limité à l'espace de travail, hooks désactivés. Confine par la liste
  d'outils, pas par le système.

Dans les deux cas, l'usine garde la main sur les processus qu'elle lance (le lanceur borné
`CappedRun` / `_kill_tree` de v1 est conservé) et c'est elle, pas l'agent, qui démarre le
produit pour le smoke.

### 4.4 Ce que l'usine vérifie (P4)

1. **Environnement propre** : venv reconstruit depuis `pyproject.toml` + `uv.lock`
   (`uv sync --frozen`), `npm ci` pour le frontend. Une dépendance absente du manifest fait
   échouer la vérification, pas la collecte (leçon Argon2).
2. **Suite complète** : `uv run pytest --json-report`, parsing par
   `orchestrator/pytest_report.py` (conservé). Vitest pour le frontend.
3. **Tests QA intouchés** : empreinte SHA des fichiers de tests écrits par la phase QA ;
   toute différence = échec de la story (le `TEST_TAMPER_GUARD=strict` de v1, sans le
   mode warn).
4. **Traçabilité** : chaque critère de la story a au moins un nodeid vert (marqueur
   `# AC:` ou JSON de sortie) ; sinon la story n'est pas `done`
   (`orchestrator/traceability.py` conservé, réduit).
5. **Smoke** selon profil : bibliothèque = import du package ; CLI = `main.py --help` sort 0
   avec une sortie non vide ; API = démarrage + `GET /health` 200 ; fullstack = idem +
   build frontend.

### 4.5 État, API, interface

- `models.py` : conservé et réduit (`ProjectState`, `Epic`, `UserStory`,
  `AcceptanceCriterion`, `PlannedTest`, `ChatMessage`, `Usage`). Les modèles
  streams/tasks/observations/gouvernance/calibration sont retirés du noyau ; le chargeur
  ignore les champs inconnus pour lire les anciens états.
- `storage.py`, `orchestrator/events.py` (bus + SSE), `orchestrator/workspace.py`
  (scaffold) : conservés.
- `api/server.py` : réduit aux ~20 endpoints du noyau (projets CRUD, start/stop/pause,
  chat, stories edit/add/delete/reorder/rebuild/force-done, files, diff, stream SSE,
  provider). Les 50 autres disparaissent avec leurs mécanismes.
- Frontend : conservé tel quel en phase 1-3 (les panneaux sont déjà conditionnés à la
  présence des données), élagué en phase 5.

### 4.6 Configuration v2 (exhaustive)

`AGENT_PROVIDER`, `CLAUDE_CMD`, `CLAUDE_MODEL`, `MODEL_PLAN` (optionnel), `WORKSPACE_ROOT`,
`AGENT_TIMEOUT_S`, `DEV_MAX_ATTEMPTS`, `DEV_MAX_TURNS`, `PROJECT_BUDGET_USD`,
`SMOKE_TIMEOUT_S`, `CONFINEMENT` (`docker` | `host`), `FAKE_AGENTS` (tests uniquement).
Douze réglages. Un treizième se justifie devant le banc.

### 4.7 Arborescence cible

```
backend/autospec/
  core/
    machine.py        états, transitions, événements           (~300 lignes)
    pipeline.py       enchaînement brief/plan/build/deliver     (~400)
    agent.py          lancement Claude Code natif, confinement   (~250)
    verify.py         env propre, suite, empreintes, traçabilité (~300)
    prompts.py        pm, po, qa, dev : 4 prompts                (~350)
    profiles.py       lib / cli / api / fullstack : smoke + scaffold (~150)
  models.py           réduit                                     (~300)
  storage.py, orchestrator/events.py, orchestrator/workspace.py, orchestrator/pytest_report.py
  api/server.py       réduit                                     (~500)
```

Cible totale du noyau : moins de 2 500 lignes hors API et modèles. Pas de BMAD : les
personas de repli de `personas.py` (quatre rôles) suffisent et retirent la dépendance à
`Brainstorming/_bmad` et l'« override programmatique » qui combat ses menus.

### 4.8 Hors périmètre du noyau (candidats de phase 4 ou abandonnés)

Streams et worktrees, merge et canari, décomposition en tâches, split-on-failure, Technical
Stories, refine critic / judge, revue de plan, architecte, constitution, gouvernance,
observations, knowledge, cartographe, pattern detector, policy, scorecard, rétro,
évaluateur, revue sécurité, livraison Docker, sandbox Docker du produit, tech-writer,
components, language selector (Python seul en v2), brainstorming, boucle auto-spec,
analyst, session monitor ccusage, escalade de modèle, classifier, arbitrage, amendement,
réservations budgétaires, bootstrap de projet, plan gates, claims et arbitre de claims,
dependency coordinator, source reviewer GPT, isolated validation, delivery evidence,
contrats d'acceptance scellés, fournisseurs LangChain (interface `AgentRunner` conservée).

## 5. Banc de mesure

Le banc existe avant le noyau. Il est la définition opérationnelle de « ça marche ».

### 5.1 Projets

| Id | Projet | Profil | Taille attendue | Origine |
|---|---|---|---|---|
| B1 | Slugify lib | bibliothèque | 1 story, 1 fichier | `scripts/build_driver.py` brief 1 |
| B2 | Todo CLI | cli | 3-4 stories | brief 2 |
| B3 | Notes API | api (FastAPI + SQLite) | 4-6 stories, CRUD + validation | nouveau brief, inspiré de `notes-api-d401ea07` |
| B4 | Counter webapp | fullstack (React + FastAPI) | 3 stories | brief 3 (`drv-p3`) |
| B5 | Relais Support | fullstack réaliste, 57 critères | 7 lots | `docs/validation/support-client/01_specification.md` |

B1 à B4 sont joués à chaque gate. B5 est le projet de fin de phase 5 uniquement (coût et
durée), avec son référentiel indépendant de 57 critères comme oracle.

Les briefs sont figés dans `bench/briefs/*.md` avec leur hash ; une modification de brief
crée une nouvelle version du banc et interdit la comparaison silencieuse.

### 5.2 Métriques (par run)

| Métrique | Définition | Lecture |
|---|---|---|
| M1 complétion | l'itération atteint `DONE` sans intervention humaine | oui / non ; c'est LA métrique |
| M2 durée | mur, de la création du projet à l'état final | minutes |
| M3 coût | USD remontés par le fournisseur (ou tokens si abonnement) | USD |
| M4 appels agents | nombre de sessions fournisseur | entier |
| M5 vert en environnement propre | suite du produit rejouée par le banc dans un venv neuf | passed / failed / collecte KO |
| M6 oracle caché | % des contrôles de l'oracle indépendant du banc qui passent (boîte noire via l'interface publique fixée par le brief) | % |
| M7 smoke | le produit démarre et répond selon son profil | oui / non |
| M8 interventions | nombre d'actions humaines nécessaires pour arriver à M1 | entier (0 attendu) |

M5 à M7 sont calculées par le banc lui-même, hors de l'usine mesurée (oracle indépendant).

### 5.3 Configurations comparées

| Config | Description | Rôle |
|---|---|---|
| A : v1 actuelle | `main` au commit de référence, `.env` de production tel quel | baseline « ce qu'on a » |
| B : harness nu | une seule session `claude -p` dans un dépôt scaffoldé : brief + « implémente en TDD, suite verte » | baseline « ce que fait le harness seul » |
| C : v2 | le noyau de ce plan | la cible |

Même modèle pour les trois (figé par campagne, `claude-sonnet-5` pour le coût sauf décision
contraire ; une campagne opus séparée si le budget le permet). N = 2 runs par cellule pour
voir la variance ; B5 N = 1.

Estimation de coût d'une campagne complète A + B + C sur B1-B4 : A ≈ 60-120 $ (15 à 50 $ le
projet observé), B ≈ 5-10 $, C ≈ 10-25 $. Les gates suivantes ne rejouent que C (10-25 $).

### 5.4 Outillage

`backend/bench/` (nouveau, indépendant de l'usine) :
- `run.py --config A|B|C --project B1..B5 --n 2` : crée le projet par l'API, suit le SSE,
  attend l'état final ou le plafond de mur, puis calcule M5-M7 hors usine ;
- résultats en `docs/bench/<date>/<config>/<project>-<n>.json` ;
- `report.py` : tableau agrégé dans `docs/bench/README.md` (une ligne par campagne, jamais
  écrasée).

`scripts/build_driver.py` (briefs seedés, cap de mur, résumé JSON) et le `verify_app.js`
existant servent de base ; `tools/support_benchmark_campaign.py` (REM-25) n'est pas repris.

### 5.5 Règle de décision

Un incrément du noyau ou un mécanisme réintroduit est mergé si, sur B1-B4 :
1. M1 ne diminue sur aucun projet ;
2. M5, M6, M7 ne diminuent sur aucun projet ;
3. M2 et M3 n'augmentent pas de plus de 25 % sans gain sur M1 ou M6.

Un mécanisme de la liste 4.8 n'est réintroduit que s'il améliore M1 ou M6 sur au moins un
projet sans violer 1 à 3. Le résultat du banc est joint au commit (lien vers le JSON).

## 6. Garder / jeter / réévaluer

Légende : **G** garder tel quel, **R** garder en réduisant, **E** réévaluer sur le banc en
phase 4, **J** jeter (gelé sur la branche d'archive `v1-archive`, jamais supprimé de
l'historique).

### 6.1 Modules backend

| Module | Lignes | Verdict | Motif |
|---|---|---|---|
| `orchestrator/pipeline.py` | 11 685 | **J** | remplacé par `core/` ; on en extrait `CappedRun` et `_kill_tree` |
| `agents/runner.py` | 1 085 | **R** | garder `ProcessRegistry`, `AgentResult`, `AgentError`, le protocole `AgentRunner`, le job Windows ; jeter le mode médié, l'attestation d'isolation, les sessions rejouées |
| `agents/file_broker.py` | ~250 | **J** | protocole JSON de fichiers : l'agent natif n'en a plus besoin ; la liste `_PROTECTED` inspire la liste blanche |
| `agents/prompts.py` | 2 730 | **R** | 4 prompts sur 72 : `pm_interview`, `po_plan`, `qa_test_plan`, `dev_story` réécrits courts |
| `agents/personas.py` | 252 | **R** | 4 personas de repli, sans BMAD |
| `agents/scripted.py` | 593 | **J** | réponses en boîte couplées aux marqueurs de prompts ; `FakeRunner` suffit aux tests, la démo UI repart sur un état enregistré |
| `agents/providers.py`, `discovery.py` | 577 | **E** | fournisseurs LangChain / OpenRouter / Ollama : hors noyau, interface conservée |
| `config.py` | 1 283 | **J** | remplacé par 12 réglages |
| `models.py` | 849 | **R** | voir 4.5 |
| `storage.py` | 219 | **G** | |
| `orchestrator/events.py` | 63 | **G** | bus + ring + SSE |
| `orchestrator/workspace.py` | 639 | **R** | scaffold, gitignore ; retirer les parties streams |
| `orchestrator/pytest_report.py` | 29 | **G** | |
| `orchestrator/traceability.py` | 198 | **R** | marqueurs `# AC:` et nodeids ; sans alias multi-stream |
| `orchestrator/profiles.py` | 162 | **R** | lib / cli / api / fullstack ; sans brownfield |
| `orchestrator/toolchain.py` | 303 | **R** | commandes uv / npm ; Python et Node seulement |
| `orchestrator/delivery_gate.py`, `delivery_state.py` | 215 | **R** | la DoD devient les 5 contrôles de 4.4 |
| `orchestrator/guards.py` | 393 | **R** | garder l'empreinte des tests QA (tamper) ; jeter scope / skeleton / import guards (warn jamais exploité) |
| `orchestrator/refine.py` | 193 | **E** | maker / critic / judge sur le plan : candidat n°2 de phase 4 |
| `orchestrator/plan_pipeline.py` | 1 213 | **E** | PO multi-étapes, jamais activé en réel ; candidat si le plan mono-passe échoue sur B3-B5 |
| `orchestrator/streams.py`, `scheduler.py`, `independence.py` | 749 | **E** | parallélisme : dernier candidat de phase 4 |
| `orchestrator/session_monitor.py` | 142 | **E** | fenêtre d'abonnement ; utile mais hors noyau |
| `orchestrator/recovery.py`, `classifier.py` | 241 | **J** | jamais branchés |
| `orchestrator/constitution.py`, `governance.py`, `observations.py`, `knowledge.py`, `cartographer.py`, `pattern_detector.py`, `policy.py`, `scorecard.py`, `amendment.py`, `arbitration.py`, `lessons.py`, `forecast.py`, `mutation.py`, `signatures.py`, `schema.py`, `manifests.py` | ~4 500 | **J** | boucle V3 et swarm : aucune preuve de valeur, jamais joués en production avec succès |
| `orchestrator/docker_deploy.py`, `deploy.py`, `sandbox.py`, `setup_exec.py`, `runtime_acceptance.py` | ~1 900 | **E** | livraison Docker et acceptance navigateur : phase 4, après B4 vert |
| `orchestrator/isolated_validation.py`, `validation_environment.py`, `bootstrap.py`, `dependencies.py`, `budget_reservations.py`, `owned_publication.py`, `plan_gates.py`, `prebuild_resume.py`, `stack.py` | ~5 100 | **J** | octobre : le principe « env propre » passe dans `core/verify.py` en 50 lignes ; le reste est jeté |
| `validation/*` (product_harness, browser_contracts, coordinator, quality / security / business / architecture contracts, delivery_evidence, source_reviewer, native_quality_raccord) | ~8 000 | **J** | oracle de B5 : le banc utilise le référentiel de 57 critères directement, pas cette machinerie |
| `orchestrator/skills.py`, `skills/*`, `skill_validation.py` | ~230 + skills | **E** | catalogue de skills dans le prompt : candidat de phase 4 |
| `orchestrator/build_monitor.py`, `interactions.py`, `observability.py`, `metrics.py` | 340 | **R** | timeline JSONL par projet et compteur d'usage ; sans Langfuse en v2 |
| `language_selector.py`, `spec_import.py`, `orchestrator/brownfield.py` | 132 | **J** | Python seul en v2 ; brownfield plus tard |
| `api/server.py` | 1 665 | **R** | ~20 endpoints |

### 6.2 Principes d'octobre conservés (sans leur code)

- Une dépendance absente du manifest n'est pas une dépendance (REM-04).
- Une suite n'est verte qu'en environnement reconstruit depuis manifest + lock (REM-05).
- Les tests de référence sont intouchables et leur empreinte est vérifiée (REM-06).
- L'oracle d'acceptance vit hors du dépôt du produit (REM-09) : c'est le banc.
- L'usine ne tue que les processus qu'elle a créés (REM-02) : `ProcessRegistry`.

### 6.3 Frontend

12 700 lignes TypeScript, 31 fichiers de tests, 321 tests Vitest. **R** : conservé pendant
les phases 1-3 ; en phase 5, retrait des panneaux sans données (observations, gouvernance,
knowledge, graphe de dépendances, streams) et de leurs types.

### 6.4 Documentation

| Document | Verdict |
|---|---|
| `docs/REFONTE_V2.md` (ce plan), puis `docs/STATE.md` | source unique |
| `docs/validation/support-client/01_specification.md`, `02_requirements_verification.md` | **G** : brief et oracle de B5 |
| `README.md` | réécrit en phase 5, court |
| `how_it_works.md`, `FEATURES.md`, `BACKLOG.md`, `todo_tasks.md`, `REFACTOR_PLAN.md`, `RFC-*.md`, `VERIFIED_SWARM_UPGRADE.md`, `WORKFLOW_REVIEW.md`, `GENERATION_FUSION_REVIEW.md`, `FACTORY_IMPROVEMENTS.md`, `DEFECTS_RESOLUTION_PLAN.md`, `handle_project_def_and_create.md`, `DOCKER_DELIVERY.md`, `docs/NEXT_STEPS_2026-09.md`, `docs/improvement_V3.md`, `docs/Plan_Complet_*.md`, `docs/SUPERVISED_RUN_*.md`, `docs/validation/support-client/03_*.md`, `04_*.md`, `docs/ux/*` | `docs/archive/` en phase 5, avec un index d'une ligne par document |
| `artifacts/remediation/*` | gelé sur la branche d'archive, retiré de `main` |

## 7. Séquencement

Chaque phase a un critère de sortie mesuré. Pas de phase suivante sans ce critère.

### Phase 0 : baseline et spikes (2 à 3 sessions, ~100-150 $ de runs)

1. Synchroniser le venv, obtenir l'état réel de la suite v1, figer le commit de référence
   `v1-ref` et créer la branche `v1-archive`.
2. Écrire `backend/bench/` (section 5.4) et les briefs B1-B4 figés.
3. Jouer A (v1) et B (harness nu) sur B1-B4, N = 2. Archiver dans `docs/bench/<date>/`.
4. Spike confinement : image `autospec-agent`, un `claude -p` avec outils natifs dans le
   conteneur sur B1 ; mesurer si Docker Desktop (session Windows) tient. Décision A ou B
   de la section 4.3 consignée dans ce document.
5. Spike sans code : rédiger les 4 prompts v2 et les jouer à la main sur B2 avec Claude Code
   nu pour calibrer leur longueur et leur sortie JSON.

Sortie : tableau baseline A et B publié ; décision de confinement prise ; prompts calibrés.

### Phase 1 : noyau séquentiel, profils lib et cli (3 à 5 sessions)

1. `core/machine.py` en TDD pur avec `FakeRunner` (états, transitions, événements,
   persistance, reprise après redémarrage).
2. `core/agent.py` : lancement natif confiné, parsing JSON, usage, timeouts, kill.
3. `core/verify.py` : env propre, suite, empreintes QA, traçabilité.
4. `core/pipeline.py` + `core/prompts.py` + `core/profiles.py` (lib, cli).
5. `api/server.py` : création de projet avec `engine: "v2"` (sélection par projet, pour
   jouer A et C côte à côte sur le même backend ; disparaît en phase 5).

Sortie : C sur B1 et B2, N = 2 : M1 = oui à chaque run, M5-M7 verts, M3 et M2 inférieurs à
A. Suite unitaire du noyau sous 30 s.

### Phase 2 : profil api, smoke HTTP, traçabilité stricte (2 à 3 sessions)

Profil api (FastAPI + SQLite), smoke HTTP, câblage `main.py` déterministe dans le scaffold
(leçon « 19 US vertes, aucun serveur »).

Sortie : C sur B3, N = 2 : M1 = oui, M6 ≥ 90 %.

### Phase 3 : profil fullstack (2 à 3 sessions)

Frontend React + Vite dans le même dépôt, stories frontend séquentielles après le backend,
smoke = backend + build frontend + `GET /` servi. Aucun worktree.

Sortie : C sur B4, N = 2 : M1 = oui ; B1-B4 tous verts, tableau complet A / B / C publié.

### Phase 4 : réintroduction mesurée (durée ouverte, un candidat par session)

Ordre proposé, chacun jugé par la règle 5.5 :
1. Relance ciblée après échec (relancer la story avec la sortie pytest, sans
   re-décomposer).
2. Revue de plan (critic / judge, `refine.py`) : mesurée sur M6 de B3 et B4.
3. Split-on-failure (re-découpage d'une story qui échoue N fois).
4. Catalogue de skills dans le prompt dev.
5. Session monitor (fenêtre d'abonnement).
6. Livraison Docker (profil fullstack).
7. Parallélisme de stories indépendantes : en dernier, et seulement si M2 est devenu la
   métrique limitante.

Tout candidat qui échoue la règle est consigné dans `docs/STATE.md` avec ses chiffres et
abandonné.

### Phase 5 : décommission et B5 (2 sessions + 1 run long)

1. Retrait de `engine`, suppression du code v1 de `main` (il vit sur `v1-archive`),
   élagage du frontend, 12 réglages, suite backend complète sous 2 min.
2. Documentation : `README.md` court, `docs/STATE.md`, `docs/archive/`.
3. Run B5 (Relais Support) avec le référentiel de 57 critères comme oracle. Le résultat,
   quel qu'il soit, est publié dans `docs/bench/` et devient la baseline de la suite.

## 8. Méthode de travail pour construire la v2

Ce projet a été vibe-codé par couches successives ; la v2 se construit autrement, et cette
méthode est aussi importante que le périmètre.

1. **Un incrément = une story de l'usine elle-même**, avec ses critères d'acceptance et son
   test rouge avant le code. Le backlog v2 tient dans `docs/STATE.md`, pas dans un essaim de
   documents.
2. **Deux niveaux de tests, rien entre les deux** : la suite unitaire du noyau (hermétique,
   `FakeRunner`, sous 30 s, jouée à chaque commit) et le banc (réel, payant, joué aux gates).
   Pas de tests d'intégration qui mockent la moitié du monde et pèsent 45 000 lignes.
3. **Pas de drapeau pour « garder l'ancien comportement »**. Si un comportement change, il
   change ; le banc dit si c'était une bonne idée.
4. **Un rédacteur à la fois sur le noyau.** Les essaims d'agents (Workflow, Codex en
   parallèle) restent possibles pour le banc, les briefs, la documentation, l'élagage du
   frontend ; jamais pour `core/`.
5. **Chaque session se termine par une entrée dans `docs/STATE.md`** : ce qui a été fait, le
   résultat du banc si joué, la prochaine étape. C'est le seul journal.
6. **Interdits explicites** : `ruff check` sans `--no-fix` (réécrit les fichiers), tuer un
   processus par nom, modifier un brief du banc sans nouvelle version, merger sans chiffres.

## 9. Risques et questions ouvertes (tranchées en section 10)

1. **Outils natifs et abonnement Claude Code.** La décision du 12 octobre (« génération
   seule dans Claude, revues par GPT ») et le mode médié semblent motivés à la fois par le
   confinement et par l'usage de l'abonnement plutôt que de l'API. La v2 suppose qu'un
   `claude -p` avec outils natifs, confiné dans un conteneur ou par liste blanche, est
   acceptable. À confirmer explicitement ; sinon, l'alternative est l'API Anthropic avec
   un agent à outils côté usine (plus cher, mais l'agent voit ses tests).
2. **Docker Desktop sur Windows.** L'option A de confinement dépend de Docker dans la bonne
   session utilisateur (incident du 20 juillet). Le spike de phase 0 tranche ; l'option B
   est le repli.
3. **Budget de la baseline.** Jouer v1 sur B1-B4 à N = 2 coûte 60-120 $ pour des chiffres
   qu'on connaît à moitié (46,88 $ pour B4). Alternative : N = 1 pour A, N = 2 pour B et C.
4. **Sort des 272 commits d'octobre.** Proposition : branche `v1-archive` figée au commit de
   référence, `artifacts/remediation/` et le paquet `validation/` retirés de `main` en phase
   5. Les principes sont conservés (6.2), pas le code.
5. **B5 comme étoile polaire.** Le référentiel de 57 critères est exigeant (Argon2, CSRF,
   sessions, concurrence). Garder B5 comme mesure de fin de phase 5 est utile ; en faire la
   cible des phases 1-4 reproduirait l'erreur d'octobre.
6. **Modèle du banc.** Sonnet pour le coût, ou Opus pour la qualité ? Proposition : Sonnet
   pour toutes les gates intermédiaires, une campagne Opus en fin de phase 3 et en phase 5.
7. **Fournisseurs autres que Claude Code.** Codex natif est le second candidat naturel pour
   `core/agent.py` (même principe : harness avec outils). LangChain / OpenRouter / Ollama
   restent hors noyau tant qu'un besoin mesuré n'apparaît pas.
8. **Frontend.** 12 700 lignes pour piloter un pipeline de 2 500 : garder tel quel en
   phase 1-3 est pragmatique, mais l'élagage de phase 5 sera lourd. Alternative : geler le
   frontend actuel et en construire un minimal (board + chat + run) en parallèle, par un
   agent séparé, à partir de `docs/ux/`.

## 10. Décisions du 2 novembre 2026

L'utilisateur a délégué l'arbitrage des questions de la section 9. Décisions prises, avec leur
justification :

1. **Outils natifs : oui.** Spike réel du 2 novembre : `claude -p --restricted --safe-mode
   --strict-mcp-config --tools Read,Edit,Write,Glob,Grep,Bash --allowedTools Read Edit Write Glob
   Grep "Bash(uv run pytest:*)" ... --permission-mode dontAsk --permission-prompts none` dans un
   projet uv jetable : l'agent écrit le code, lance `uv run pytest` jusqu'au vert, 23 s, 0,04 $ ;
   `tasklist` est refusé et remonté dans `permission_denials`. L'abonnement est conservé (CLI).
2. **Confinement : option B (liste blanche) d'abord.** Elle empêche les commandes accidentelles
   (l'incident du 8 octobre), pas un agent malveillant : un test écrit par l'agent puis lancé par
   `uv run pytest` peut exécuter du code arbitraire. L'option A (conteneur) reste au programme
   de la phase 4, mesurée comme les autres. `--safe-mode` coupe aussi CLAUDE.md, hooks et
   skills de l'utilisateur : les sessions de l'usine sont hermétiques.
3. **Baseline :** N = 1 pour A (v1) sur B1 et B2 seulement, B4 étant déjà documenté
   (`build-logs/p3`, 46,88 $, timeout) ; N = 1 pour B et C au premier passage, N = 2 aux gates.
4. **Octobre :** tag `v1-ref` et branche `v1-archive` posés sur `5dea3e71` ; la v2 se construit
   sur la branche `refonte-v2`. Rien n'est supprimé avant la phase 5.
5. **B5** reste la mesure de fin de phase 5 uniquement.
6. **Modèle :** `sonnet` pour toutes les sessions du banc (A, B, C), y compris en forçant tous
   les modèles par rôle de v1. Campagne Opus séparée en fin de phase 3.
7. **Codex et LangChain :** hors noyau ; l'interface `AgentRunner` (`core/ports.py`) les
   accueillera si une mesure le justifie.
8. **Frontend : la v2 est d'abord sans interface.** Une CLI (`python -m autospec.core`) suffit
   au banc ; le choix « élaguer l'existant ou en refaire un minimal » est reporté après la
   phase 3, quand on saura ce que le noyau expose réellement.

Ajustements du plan qui en découlent :

- **M6 redéfinie** (section 5.2) : la couverture des critères auto-déclarée par une usine n'est
  pas comparable entre configurations. Chaque brief du banc fixe l'interface publique (noms,
  commandes, routes, codes de sortie) et un oracle caché, écrit par le banc, la teste en boîte
  noire. La traçabilité critère / test reste un contrôle interne du noyau (section 4.4).
- **P7 précisé** : un rédacteur par FICHIER, contrats écrits avant (`docs/v2/CONTRACTS.md`). Les
  modules feuilles du noyau (`agent.py`, `verify.py`, `profiles.py`, `prompts.py`, `plan.py`) et le
  banc sont écrits en parallèle par des sous-agents ; le pipeline, la machine à états et
  l'intégration restent à un seul rédacteur.
- **QA écrit les tests d'acceptance exécutables**, le dev ne peut pas y toucher : la phase QA
  produit `tests/acceptance/test_us_<n>.py`, l'usine vérifie qu'ils sont ROUGES avant
  l'implémentation (un test qui passe déjà ne vérifie rien), les empreinte et les commite. Le
  rouge-vert du TDD est ainsi contrôlé par l'usine, pas seulement demandé à l'agent.
- **Pas de `--max-turns`** dans le CLI 2.1.301 : une session est bornée par son timeout et son
  budget (`--max-budget-usd`). Réglages v2 préfixés `AUTOSPEC2_` (`core/settings.py`).

## 11. Premiers résultats du banc (2 novembre 2026)

Tableau complet : `docs/bench/README.md`. Modèle `sonnet` partout, N = 1.

| Projet | A : v1 actuelle | B : harness nu | C : v2 |
|---|---|---|---|
| B1 slugify (lib) | ne démarre pas | 0,5 min, 0,04 $, oracle 12/12 | 4,5 min, 0,38 $, oracle 12/12 |
| B2 todo (cli) | ne démarre pas | 1,0 min, 0,08 $, oracle 10/10 | 7,2 min, 0,62 $, garé sur US-5 puis repris : oracle 10/10 |
| B3 notes (api) | non joué | 0,8 min, 0,08 $, oracle 15/15 | 12,9 min, 0,74 $, oracle 15/15 |

Lecture :

1. **v1 ne démarre plus sans Docker.** Depuis la remédiation d'octobre, son préflight exige un
   moteur Docker Linux (`ISOLATION_UNAVAILABLE ... no host fallback`) et se gare avant tout appel
   d'agent. Référence historique (septembre, avant octobre) : Todo CLI en 38 min pour 17,36 $,
   Counter webapp arrêtée par timeout à 2 h pour 46,88 $.
2. **La v2 tient sa promesse de fiabilité** : trois produits corrects (oracle à 100 %, suites vertes
   en environnement propre, smoke OK), 13 stories sur 13 vertes à la première tentative de dev,
   25 à 60 fois moins cher que v1 en septembre. Deux défauts du noyau trouvés par les runs réels
   et corrigés le jour même (règle « tout rouge » trop stricte, story déjà satisfaite par les
   précédentes).
3. **Mais le harness nu fait aussi bien, dix fois plus vite et moins cher.** Sur des briefs
   précis dont l'interface publique est fixée, une seule session Claude Code confinée livre le
   produit parfait en moins d'une minute. Selon la règle 5.5 de ce plan, le pipeline v2 dans sa
   forme actuelle ne gagne pas sa place sur B1 à B3 : son coût est un surcoût par story (QA,
   dev, deux reconstructions d'environnement propre), sans gain de qualité mesurable.

Conséquences pour la direction (à valider avec l'utilisateur) :

- La valeur différenciante n'est pas l'exécution du code (le harness la maîtrise), ni même le
  découpage en stories sur de petits produits. Elle est probablement dans trois endroits que le
  banc doit maintenant mesurer :
  1. **les produits qui dépassent une session** (B4 fullstack, B5 Relais Support et ses 57
     critères) : c'est là que le harness nu devrait commencer à échouer ;
  2. **la vérification indépendante** (environnement propre, tests d'acceptance intouchables,
     oracle hors produit, smoke), qui coûte quelques secondes et peut encadrer n'importe quel
     harness ;
  3. **la transformation d'une idée floue en brief précis** : les briefs du banc, écrits avec une
     interface contractuelle, sont exactement ce qui rend le harness si efficace.
- Piste de conception à tester : une v2 **adaptative**, où le PO ne découpe que si le produit ne
  tient pas dans une session ; un petit produit devient une seule story, et le cœur de l'usine
  devient « brief précis, session native, vérification indépendante ».

Prochaines étapes proposées, dans l'ordre :

1. Phase 3 : profil fullstack (scaffold Vite/React, commandes npm dans la liste blanche,
   vérification et smoke du frontend), puis B4 en configurations B et C.
2. B5 dans le banc (brief existant, oracle automatisé tiré du référentiel de 57 critères), en B et C.
3. Variante « une seule story » de la v2 sur B1 à B3, pour mesurer le coût minimal de la méthode.
4. N = 2 sur chaque cellule pour connaître la variance avant toute conclusion définitive.

### 11.1 Mise à jour : variance et taille adaptative (2 novembre, suite)

- **Variance** (N = 2 sur B1 à B3) : chaque run des deux configurations atteint 100 % à l'oracle.
  Le harness nu reste stable (0,5 à 1 min, 0,04 à 0,10 $) ; la v2 multi-stories varie davantage
  (le PO découpe B3 en 5 puis 7 stories, 13 puis 20 min).
- **Taille adaptative** (règle 5.5 passée) : le PO ne produit qu'une story quand le produit tient
  dans une session. Sur B1, B2 et B3, la v2 tombe à 1,4 / 2,5 / 2,9 min et 0,18 / 0,26 / 0,26 $,
  avec 100 % à l'oracle : environ trois fois moins cher que la version multi-stories, sans perte.
  L'écart avec le harness nu n'est plus que de 2 à 4 fois, soit le prix de la QA indépendante et de
  la vérification en environnement propre.
- Un défaut d'infrastructure Windows trouvé en route (remplacement atomique de l'état refusé par
  un accès concurrent au fichier) est corrigé par de courtes nouvelles tentatives.
- **Phase 3 livrée côté noyau** : profil fullstack (FastAPI + React/Vite/TypeScript, tests
  d'acceptance pytest et vitest, garde-fous sur la configuration de test du frontend), vérifié de
  bout en bout avec de vrais npm, uv et git. Mesure B4 à suivre.
