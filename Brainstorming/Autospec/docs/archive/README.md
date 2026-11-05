# Archives de la v1

Documents de la v1 d'Autospec (juin à octobre 2026), retirés de la racine du projet et de `docs/`
pendant la phase 5 de la refonte (principe P6 de [REFONTE_V2.md](../REFONTE_V2.md)). Ils décrivent
le code v1 et ses chantiers ; aucun ne décrit la v2. L'état courant est dans [STATE.md](../STATE.md).

## Code v1

- **Tag `v1-ref` et branche `v1-archive`**, posés sur `5dea3e71` (16 octobre 2026) : la v1 complète,
  documents compris, à leurs chemins d'origine. Lire un fichier sans changer de branche :
  `git show v1-ref:Brainstorming/Autospec/<chemin>`.
- Retirés de la branche `refonte-v2`, conservés seulement sur `v1-archive` : `artifacts/remediation/`
  (preuves des lots REM-00 à REM-25), `tools/support_benchmark_campaign.py` (campagne Relais Support
  d'octobre), `backend/plan_breach.json`, `backend/_ignore_probe.txt`.
- Le code v1 encore présent dans l'arbre (`backend/autospec/orchestrator`, `agents`, `api`,
  `validation`, `config.py`, `backend/tests`, `backend/scripts`, `frontend/`) est gelé, non maintenu,
  et sera retiré en phase 5.

Les fichiers ont gardé leur nom. Un document cité par son ancien chemin se trouve dans `v1/` :
racine du projet, `docs/` et `docs/validation/support-client/` vers `v1/<nom>`, `docs/ux/` vers
`v1/ux/`, `backend/build-logs/` vers `v1/build-logs/`.

## Index

Statuts : **fait** (plan réalisé ou rapport complet), **remplacé** (un document plus récent ou la v2
couvre le sujet), **abandonné** (arrêté avant la fin). Dates : création et dernière modification.

| Document | Contenu | Dates | Statut |
|---|---|---|---|
| [how_it_works.md](v1/how_it_works.md) | Documentation technique de la v1 : architecture, agents BMAD, ordonnancement, boucle auto-spec, persistance | 2026-06-12 au 2026-10-11 | remplacé par [REFONTE_V2.md](../REFONTE_V2.md) et [CONTRACTS.md](../v2/CONTRACTS.md) |
| [FEATURES.md](v1/FEATURES.md) | Inventaire des fonctionnalités de la v1 (backend FastAPI, frontend React) | 2026-06-12 au 2026-07-04 | remplacé |
| [BACKLOG.md](v1/BACKLOG.md) | Backlog priorisé (valeur, complexité) et journal des itérations de la v1 | 2026-06-12 au 2026-09-22 | remplacé par [STATE.md](../STATE.md) |
| [REFACTOR_PLAN.md](v1/REFACTOR_PLAN.md) | Plan « zéro échec perpétuel » après le blocage de `todo_list_2` (worker non fatal, merge rebasé, livraison partielle) | 2026-06-29 au 2026-07-04 | fait |
| [RFC-po-pipeline.md](v1/RFC-po-pipeline.md) | RFC du PO en trois étapes (structure, spec, Gherkin) | 2026-07-02 au 2026-07-04 | remplacé par sa révision v2 |
| [RFC-po-pipeline-v2.md](v1/RFC-po-pipeline-v2.md) | Révision : complexité de premier ordre, retour spec vers structure, un critic par étape | 2026-07-02 au 2026-07-04 | abandonné : codé derrière un drapeau, jamais activé en réel ; la v2 garde un plan en une passe à taille adaptative |
| [RFC-technical-stories.md](v1/RFC-technical-stories.md) | Technical Stories : décomposition récursive d'une tâche en échec | 2026-07-02 au 2026-07-04 | fait en v1, hors du noyau v2 |
| [ux/01-analysis-and-proposals.md](v1/ux/01-analysis-and-proposals.md) | Analyse critique de l'interface v1 et propositions | 2026-06-21 | fait (synthétisé dans 02) |
| [ux/02-ux-architecture.md](v1/ux/02-ux-architecture.md) | Architecture UX cible « mission control » et périmètre du MVP | 2026-06-21 au 2026-07-05 | fait (MVP livré) |
| [ux/03-ux-improvements.md](v1/ux/03-ux-improvements.md) | Améliorations post-MVP : phase 1 (Q#) et feuille de route phase 2 (R#) | 2026-07-06 | fait |
| [ux/ui-reference/README.md](v1/ux/ui-reference/README.md) | Index de la référence de reconstruction du frontend v1 | 2026-07-02 au 2026-07-06 | remplacé par `frontend_v2/` |
| [ux/ui-reference/01-design-system.md](v1/ux/ui-reference/01-design-system.md) | Design system du frontend v1 (tokens, thèmes, typographie) | 2026-07-02 au 2026-07-05 | remplacé |
| [ux/ui-reference/02-shell-etat-donnees.md](v1/ux/ui-reference/02-shell-etat-donnees.md) | Shell React, état global et couche données du frontend v1 | 2026-07-02 | remplacé |
| [ux/ui-reference/03-composants-majeurs.md](v1/ux/ui-reference/03-composants-majeurs.md) | Composants majeurs du frontend v1 (board, activité, run) | 2026-07-02 au 2026-07-05 | remplacé |
| [ux/ui-reference/04-composants-secondaires.md](v1/ux/ui-reference/04-composants-secondaires.md) | Composants secondaires du frontend v1 | 2026-07-02 au 2026-07-04 | remplacé |
| [WORKFLOW_REVIEW.md](v1/WORKFLOW_REVIEW.md) | Revue de bout en bout du pipeline v1 à partir du run réel `messagerie2` | 2026-07-05 | fait (corrections livrées dans le code v1) |
| [GENERATION_FUSION_REVIEW.md](v1/GENERATION_FUSION_REVIEW.md) | Analyse du dev parallèle en worktrees et du fusionneur (merge, canari, revert) | 2026-07-05 | fait (P0 à P3 livrés) |
| [VERIFIED_SWARM_UPGRADE.md](v1/VERIFIED_SWARM_UPGRADE.md) | Plan « verified swarm » : chaque tâche livrée avec un contrôle exécuté, vagues 0 à 5 | 2026-07-08 au 2026-08-15 | fait (vagues livrées derrière drapeaux) |
| [todo_tasks.md](v1/todo_tasks.md) | Suivi des tâches du verified swarm pour agents parallèles | 2026-07-08 au 2026-07-09 | abandonné : figé le 9 juillet, l'état final est dans VERIFIED_SWARM_UPGRADE.md |
| [handle_project_def_and_create.md](v1/handle_project_def_and_create.md) | Backlog PDC : définition de solution et création vérifiée du projet avant les features | 2026-07-08 | abandonné : jamais codé sous cette forme, le bootstrap de DOCKER_DELIVERY.md vise le même but |
| [DOCKER_DELIVERY.md](v1/DOCKER_DELIVERY.md) | Contrat de la livraison Docker et du bootstrap de socle technique | 2026-07-12 au 2026-10-11 | fait en v1, hors du noyau v2 (candidat de phase 4) |
| [FACTORY_IMPROVEMENTS.md](v1/FACTORY_IMPROVEMENTS.md) | Mission « first-shot fullstack » : projets créés, échecs diagnostiqués, usine corrigée | 2026-07-12 | fait |
| [Plan_Complet_Software_Factory_Agentique.md](v1/Plan_Complet_Software_Factory_Agentique.md) | Vision d'une usine auto-adaptative (humain dans, sur, puis hors de la boucle) | 2026-07-12 | remplacé par [REFONTE_V2.md](../REFONTE_V2.md) |
| [improvement_V3.md](v1/improvement_V3.md) | Boucle d'observation, gouvernance du backlog et mémoire logicielle (8 features) | 2026-07-13 | fait en v1, retiré du noyau v2 |
| [DEFECTS_RESOLUTION_PLAN.md](v1/DEFECTS_RESOLUTION_PLAN.md) | Défauts du run supervisé « recettes » du 20 juillet et leurs correctifs | 2026-07-21 au 2026-08-15 | fait |
| [NEXT_STEPS_2026-09.md](v1/NEXT_STEPS_2026-09.md) | Relecture du 22 septembre et plan des vagues 1 à 4 (budget dev, fusion, observabilité, frontend phase 2) | 2026-09-22 | fait |
| [SUPERVISED_RUN_2026-09-22.md](v1/SUPERVISED_RUN_2026-09-22.md) | Rapport du run fullstack supervisé Counter webapp (`drv-p3-9ae648a7`) | 2026-09-22 | fait |
| [build-logs/](v1/build-logs/) | Journaux du pilote `backend/scripts/build_driver.py` (p1 Slugify, p2 Todo CLI, p3 Counter webapp, p4 Counter web SSR) : baseline v1 citée par REFONTE_V2 sections 1 et 10 (p2 : 38 min, 17,36 $ ; p3 : timeout à 2 h, 46,88 $). Les `*.log` voisins sont ignorés par git | 2026-06-25 au 2026-10-11 | fait |
| [03_plan_remediation_autospec.md](v1/03_plan_remediation_autospec.md) | Programme de remédiation REM-00 à REM-25 après la campagne Relais Support du 8 octobre | 2026-10-11 au 2026-10-16 | abandonné : non clos (REM-24 ouvert, plan REM-25 rejeté), remplacé par la refonte v2 |
| [04_interfaces_remediation.md](v1/04_interfaces_remediation.md) | Contrats d'interfaces des lots parallèles de la remédiation (REM-00) | 2026-10-11 | abandonné avec le programme |
