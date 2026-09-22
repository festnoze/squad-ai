# Run fullstack supervise du 2026-09-22 (Counter webapp, drv-p3-9ae648a7)

Objectif : voir les mecanismes livres en vagues 1 et 2 (budget de requeue,
rafale canari, mode solo, compteurs de fusion, statut consolide, scaffold CLI)
travailler en reel sur un projet multi-stream, et attraper les defauts d'usine
que la suite de tests ne peut pas voir.

Pilote : `python -m scripts.build_driver 3` (brief seede « Web-app Compteur » :
FastAPI `GET /count` / `POST /increment` persiste en SQLite + frontend React),
STREAMS=1, COMPONENTS=1, SETUP_INSTALL=1, provider claude code / opus, .env de
production complet (REFINE, CONSTITUTION, EVALUATOR, SECURITY_REVIEW,
TECH_WRITER), plafond 2 h. Supervision par un moniteur sur la timeline
`build-monitor.jsonl` (phases, canari, conflits, requeues, echecs d'agent).

## Deroulement

| Heure | Evenement |
|---|---|
| 09:32 | Lancement. Spec seedee, architecte, plan PO : 1 epic, 3 stories, 8 taches (TS-1 persistance 4 taches, US-1 lecture API + affichage, US-2 increment API + bouton) |
| 09:35-10:12 | TS1-T1 (persistance SQLite) : dev 10 min, raffinement critique/juge 20 min (72/100 puis revision), 5 sondes du scope gate, merge + canari vert |
| 10:12-10:25 | TS1-T2, TS1-T3 (frontend), TS1-T4 merges, TS-1 consolidee DONE (statut stocke, vague 2) |
| 10:27-10:47 | US1-T1 (route GET) et US1-T2 (composant) merges, US-1 consolidee DONE |
| 10:48 | **Vrai conflit de merge** : US2-T1 (route POST) a ajoute le meme fichier de routage que US1-T1 (add/add, memes lignes, rebase impossible). Budget de requeue (vague 1) : branche verte conservee, tentative dev remboursee (`requeue_refunds` 1, `attempts` reste 1), requeue 1/3, regeneration sur le HEAD a jour en mode strict |
| 10:49-11:13 | US2-T1 regenere en 6 min, vert, critique/juge, merge |
| 11:16 | US2-T2 merge, US-2 consolidee DONE. 8/8 taches, 8 verdicts canari verts |
| 11:16 | **Smoke run ROUGE** : `python main.py` sort en code 0 sans ecouter (defaut D1 ci-dessous). Agent de reparation : cablage repare en 5 min, smoke vert |
| 11:21 | DoD OK avec avertissements ; **tracabilite covered=0 uncovered=12 orphans=24** (defaut D2) |
| 11:21-11:23 | Tech-writer : README redige (117 tests Python + 37 tests front rejoues) |
| 11:23 | Evaluateur : execution reelle du produit... **gel** (defaut D3) |
| 11:32 | Plafond 2 h atteint, `adispose`, mais le pilote reste bloque a la fermeture (thread lecteur) |
| 12:08 | Kill manuel du serveur genere (python 52764 -> 26848 sur :8000) ; le pilote sort, suite generee 117 verts |

## Bilan chiffre

| Mesure | Valeur |
|---|---|
| Stories / taches | 3 / 8, toutes DONE et consolidees |
| Suite generee | 117 tests Python verts, 37 Vitest verts (tech-writer), build Vite OK |
| Verification manuelle de l'app | `GET /count` -> 0 ; 2 x `POST /increment` -> 2 ; `GET /` sert le frontend React ; redemarrage -> 2 (persistance SQLite `counter.db`) |
| Calibration | suite_runs 45, items_delivered 8, suites_per_item 5.62, canary_verdicts {green: 8}, merge_requeues 1, requeue_refunds 1, canary_reverts 0, canary_batches 0, solo_requeues 0, infra_retries 0, over_budget_tasks 5, scope_violations 5 |
| Cout | 40 appels, 46,88 $ (boss 1,88 / worker 29,83 / checker 15,17), 1 h 44 de build effectif |

Mecanismes des vagues 1-2 observes en reel : budget de requeue separe (conflit
sans tentative dev consommee), statut stocke consolide, cache npm partage (npm ci
hermetique en 4 s), compteurs de fusion, scope gate par fichier. Non sollicites :
rafale canari (aucun chevauchement de merges malgre 2 devs paralleles, les
merges sont trop courts), mode solo (un seul conflit, resolu au premier requeue),
replay canari sur rouge vide (aucun rouge d'infra).

## Defauts d'usine trouves et corriges le jour meme

| # | Defaut | Cause | Fix |
|---|---|---|---|
| D1 | Smoke rouge : aucune tache n'a cree l'app FastAPI ni fait demarrer le serveur par `main.py` (jamais modifie depuis le scaffold, aucun `uvicorn` dans le projet) ; les features publiaient leurs routes dans une table en attendant un « mounter » que personne ne portait | Le bloc de planification disait qu'une feature cablee par convention « n'a besoin d'AUCUNE tache d'integration » : vrai pour les routes, faux pour l'amorcage du serveur ; la regle « main.py DOIT demarrer le serveur » n'existait que dans le prompt dev de la tache qui aurait main.py dans son perimetre | Vague 5 : garde deterministe `_ensure_web_wiring_task` (WEB_WIRING_TASK) qui ajoute une tache d'amorcage web (app factory + main.py + pyproject) en fin de chaine backend quand aucune unite ne declare main.py ; prompts plan/decompose/dev corriges ; docstring du scaffold |
| D2 | Tracabilite covered=0, 24 « orphelins » alors que les tests portent de bons marqueurs | Les devs qualifient le marqueur par l'id de TACHE (`# AC: TS1-T1.AC-1`, leur sujet de build), le rapport ne declarait que les ids qualifies par STORY (`TS-1.AC-1`) | Vague 6 : `traceability.fold_aliases` + dictionnaire d'alias tache -> story dans `_report_traceability`. Rejoue hors ligne sur ce projet : covered 9, orphans 0, 3 criteres de story (US-1.AC-4, US-2.AC-4, US-2.AC-5) reellement portes par aucune tache (trou de decomposition, a traiter cote plan) |
| D3 | Evaluateur gele 2 h, serveur genere fuite sur :8000 | `subprocess.run(uv run python main.py, timeout=20)` : au timeout seul `uv` est tue, le petit-fils uvicorn survit et tient le tube stdout, `communicate()` bloque | Vague 7 : Popen + thread lecteur daemon borne + `_kill_tree` au timeout + filet par port. Vague 8 : le meme lanceur borne (`_run_capped_process`) sert aussi la branche CLI du smoke (`main.py` et `--help`) qui portait le meme piege |

Suivis non bloquants notes : `suites_per_item` compte les sondes du scope gate
(5 par tache ici), a distinguer ou documenter ; les stories techniques
proactives (PO) n'ont pas de Gherkin (avertissement DoD systematique) ; 96
repertoires de worktrees de juillet trainent dans `workspace/_worktrees/`
(11 Mo, runs interrompus) : un balayage au demarrage, symetrique du balayage de
process, les purgerait ; le plafond du pilote a ete atteint uniquement a cause
de D3.

Dernier endroit de cette classe encore non traite : `runtime_acceptance.py` (subprocess.run sur le script node qui spawne backend et frontend), candidat direct pour le lanceur borne partage.
