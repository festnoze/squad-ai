# Autospec — backlog de fiabilisation après Relais Support

Version 1.0 — 9 octobre 2026. Document de travail pour un coordinateur et des agents parallèles.

**État : implémentation démarrée le 11 octobre 2026 sur demande utilisateur `/goal`.** Worktrees et merges autorisés, jusqu'à cinq agents souhaités ; trois sous-agents simultanés disponibles dans cette session en plus du coordinateur. Les statuts font autorité dans le tableau. La demande autorise l'exécution des 26 tâches, y compris une nouvelle qualification avec les paramètres Claude Code abonnement/Sonnet et un plafond conservateur de 40 USD estimés ; aucune activation de crédits additionnels ou API directe.

## 1. Objectif et référence de départ

Rendre Autospec capable de produire, depuis un brief, un projet reproductible et effectivement utilisable, puis de prouver sa conformité. La cible est la **fabrique**, pas une correction artisanale de Relais Support qui masquerait ses défauts.

Campagne de référence du 8 octobre : 27 tâches déclarées terminées ; environ 116 minutes avant réparation finale interrompue ; 21,81 USD estimés enregistrés, appel interrompu potentiellement non comptabilisé. Verdict indépendant : **27 FAIL, 17 PASS, 13 NOT_VERIFIED sur 57 critères**. Les 17 PASS incluent un diagnostic ; 56 critères sont obligatoires.

Sources faisant autorité :

- [Spécification v0.2](01_specification.md) et [57 critères de vérification](02_requirements_verification.md).
- [Rapport final](../../../workspace/support-benchmark-20261008/verification-report.md) et [JSON structuré](../../../workspace/support-benchmark-20261008/verification-report.json).
- [Défauts de fabrique](../../../workspace/support-benchmark-20261008/factory-analysis.md), [incident d'arrêt global](../../../workspace/support-benchmark-20261008/factory-terminal-incident.md), [contre-revue](../../../workspace/support-benchmark-20261008/counter-review.md).
- [Identité du snapshot](../../../workspace/support-benchmark-20261008/verification-snapshot.json) : commit `2a92e68cd5d2fbe9a7ead4bfebc998b94fa34bcb`, plus modification de seed laissée par Autospec ; 290 fichiers hashés.

Distinctions à conserver :

- La commande d'arrêt global des processus Python est attestée. Son lien causal avec la disparition de la fabrique est très probable, pas établi par un inventaire exhaustif avant/après.
- La dépendance Argon2 n'a jamais été déclarée dans les manifests concernés : ne pas attribuer ce défaut à un retrait lors du merge.
- Les 13 NOT_VERIFIED sont des travaux de vérification à achever, pas 13 bugs démontrés.
- Le faux positif français « vue » a déjà été corrigé pendant la campagne. Il reste à sécuriser le mécanisme général, pas à déclarer ce patch inexistant.
- Un test du produit défaillant ne démontre pas à lui seul un bug précis d'Autospec. Les tâches de contrat ci-dessous doivent établir la chaîne brief → plan → génération → contrôle.

## 2. Règles d'exécution multi-agents

### Statuts et preuve de clôture

| Statut | Signification | Transition autorisée |
|---|---|---|
| TODO | Non commencé ; l'éligibilité dépend du graphe | IN_PROGRESS après attribution et dépendances DONE |
| IN_PROGRESS | Un propriétaire, un périmètre et une base de travail identifiés | REVIEW ou BLOCKED |
| BLOCKED | Obstacle documenté, décision/prérequis précis attendu | TODO après résolution ; jamais assimilé à DONE |
| REVIEW | Implémentation et preuves remises, intégration à contrôler | DONE après revue ; sinon IN_PROGRESS |
| DONE | Intégré et vérifié sur la révision cible | Réouverture explicite si régression |

`TODO` avec dépendances non terminées n'est pas `BLOCKED` : c'est une attente normale. `REVIEW` ne libère pas les tâches dépendantes. Les tâches facultatives non réalisées restent TODO avec décision « différée », jamais DONE fictif.

Definition of Done commune :

1. Contre-exemple reproduit ou fixture de régression identifiée ; distinction entre faits de campagne et hypothèses confirmées au diagnostic.
2. Code et tests de la fabrique intégrés sans altérer le snapshot ni affaiblir le contrat v0.2.
3. Tests positifs et négatifs exécutés ; logs, codes retour, versions et révision conservés sous `artifacts/remediation/<task-id>/<run-id>/` (convention à créer à l'exécution).
4. Critères propres à la tâche satisfaits ; limites et tests non exécutés signalés, aucune dépendance ajoutée clandestinement à l'environnement.
5. Revue indépendante des changements critiques ; coordinateur seul habilité à inscrire DONE dans ce document.

### Attribution, fichiers partagés et intégration

- Le coordinateur est **l'unique rédacteur du tableau de suivi et du journal**. Chaque agent remet un compte rendu distinct ; pas d'édition concurrente de ce Markdown.
- Avant départ : propriétaire, commit/base et modifications préexistantes, fichiers revendiqués, répertoires de tests, ressources temporaires et dépendances sont enregistrés. Aucun reset ou nettoyage global du dépôt sale de l'utilisateur.
- Les périmètres ci-dessous sont des points d'entrée observés, pas des permissions aveugles. Relire le code courant et les instructions locales avant implémentation ; les noms de modules proposés ne sont pas des fichiers supposés existants.
- **Un seul rédacteur à la fois** pour `backend/autospec/orchestrator/pipeline.py`, `backend/autospec/agents/prompts.py`, `backend/autospec/models.py`, les manifests/locks et les fichiers frontend de types partagés. Le coordinateur gère ces verrous, même entre tâches indépendantes dans le graphe.
- Préférer des modules et tests spécialisés avec interfaces convenues par REM-00. Un agent sans verrou remet une proposition de raccordement ; le coordinateur ou l'agent détenteur l'intègre. Le même fichier ne devient pas parallèle parce que les fonctions visées sont différentes.
- Tout élargissement de périmètre est demandé **avant écriture**. Si le besoin touche un propriétaire actif, suspendre cette écriture et résoudre le conflit ; ne pas supprimer un import nécessaire pour satisfaire artificiellement le périmètre.
- Les tâches peuvent être préparées en parallèle, mais leur intégration se fait sur la dernière base et déclenche les suites communes. Une branche verte seule ne suffit pas.
- Aucun arrêt par nom d'exécutable, aucun `prune`, aucun effacement de base/volume global. Nommer et inspecter les seules ressources de test avant nettoyage.
- Les essais de commandes hostiles s'exécutent uniquement dans une isolation jetable ; ne jamais reproduire l'arrêt global sur l'hôte utilisateur.

### Priorités

- **P0** : confinement ou fiabilité des preuves ; interdit de relancer une génération non fiable tant que ces protections ne sont pas validées.
- **P1** : conformité du produit, orchestration et acceptation de bout en bout.
- **P2** : optimisation après mesures ; ne retarde pas une première requalification correcte.

## 3. Tableau de pilotage — source unique des statuts

`—` signifie non attribué/non exécuté. Dépendances = IDs devant être DONE. « Toutes P0/P1 » inclut REM-01 à REM-22 et REM-00 ; exclut REM-23, REM-24 et REM-25 eux-mêmes.

| ID | Priorité | Tâche | Lot / compétence | Dépendances | Statut | Propriétaire | Preuve / révision |
|---|---|---|---|---|---|---|---|
| REM-00 | P0 | Contrats d'interface et plan d'intégration | Coordination | — | DONE | Coordinateur | 04_interfaces_remediation.md ; interfaces et exemples revus |
| REM-01 | P0 | Confinement réel des agents | Exécution | REM-00 | TODO | — | — |
| REM-02 | P0 | Cycle de vie des processus possédés | Exécution | REM-01 | TODO | — | — |
| REM-03 | P0 | État durable et récupération après interruption | Orchestration | REM-02 | TODO | — | — |
| REM-04 | P0 | Dépendances et manifests dans le workflow | Reproductibilité | REM-00 | TODO | — | — |
| REM-05 | P0 | Validation dans un environnement propre | Reproductibilité | REM-04 | TODO | — | — |
| REM-06 | P0 | Interdire les preuves de tests affaiblies | Qualité | REM-05 | TODO | — | — |
| REM-07 | P0 | Réparations bornées et classifiées | Orchestration | REM-03, REM-06 | TODO | — | — |
| REM-08 | P1 | Décision de stack structurée | Fondation | REM-00 | TODO | — | — |
| REM-09 | P1 | Contrat exécutable indépendant du code produit | Contrats | REM-00 | TODO | — | — |
| REM-10 | P1 | Admission du plan par contraintes et findings | Planification | REM-08, REM-09 | TODO | — | — |
| REM-11 | P1 | Claims normalisés et dépendances communes | Planification | REM-04, REM-10 | TODO | — | — |
| REM-12 | P1 | Conflits dynamiques de propriété des fichiers | Ordonnancement | REM-11 | TODO | — | — |
| REM-13 | P0 | Socle déterministe et sondes initiales | Fondation | REM-05, REM-08 | TODO | — | — |
| REM-14 | P0 | Première tranche métier réellement fonctionnelle | Acceptation | REM-06, REM-09, REM-13 | TODO | — | — |
| REM-15 | P1 | Pack de contrats sécurité et comptes | Contrats sécurité | REM-09 | TODO | — | — |
| REM-16 | P1 | Pack de contrats métier et concurrence | Contrats métier | REM-09 | TODO | — | — |
| REM-17 | P1 | Pack DB, API et cohérence frontend/backend | Contrats architecture | REM-09 | TODO | — | — |
| REM-18 | P1 | Pack UX, session et erreurs réseau | Contrats frontend | REM-09 | TODO | — | — |
| REM-19 | P1 | Suites complètes, couverture et six E2E | Qualité | REM-14, REM-15, REM-16, REM-17, REM-18 | TODO | — | — |
| REM-20 | P1 | Image finale, persistance et documentation | Livraison | REM-14, REM-19 | TODO | — | — |
| REM-21 | P1 | Gate finale indépendante et traçabilité | Acceptation | REM-19, REM-20 | TODO | — | — |
| REM-22 | P1 | Télémétrie des attentes, coûts et phases | Observabilité | REM-00 | TODO | — | — |
| REM-23 | P2 | Réservation budgétaire concurrente, optionnelle | Optimisation | REM-07, REM-22 | TODO | — | — |
| REM-24 | P1 | Contre-revue intégrée de la fabrique | Intégration | Toutes P0/P1 REM-00 à REM-22 | TODO | — | — |
| REM-25 | P1 | Nouvelle campagne et comparaison indépendante | Qualification | REM-24 + autorisation de lancement | TODO | — | — |

### Vagues suggérées, sans contourner les dépendances

1. REM-00 seul : fixer les interfaces minimales et la propriété des raccordements.
2. En parallèle : REM-01 (exécution), REM-04 (dépendances), REM-09 (contrat). REM-08 et REM-22 utilisent les créneaux disponibles.
3. Poursuivre indépendamment les chaînes REM-02→03, REM-05→06, REM-10→11→12 et REM-13. Les raccordements partagés restent sérialisés.
4. REM-15, REM-16, REM-17, REM-18 se répartissent les domaines après REM-09. REM-07 et REM-14 avancent dès que leurs prérequis sont acquis.
5. REM-19→20→21, puis REM-24 et REM-25. REM-23 est une piste séparée, jamais un prérequis de la sécurité ou de la requalification.

Limiter le nombre d'agents au nombre de périmètres réellement indépendants et aux créneaux disponibles. Ne pas reproduire « deux running » pour un seul appel effectif sans l'afficher.

## 4. Fiches exécutables

Les statuts/propriétaires restent uniquement dans le tableau précédent. Chaque fiche précise le travail et la preuve attendue ; les critères du référentiel cité ne sont pas remplacés par ces résumés.

### REM-00 — Contrats d'interface et intégration

- **Constat :** contrats communs, racines et responsabilités ont divergé entre tâches.
- **Livrable :** note courte validée par le coordinateur : objet d'exécution isolée et ressources possédées ; résultat de gate (`pass/fail/not_verified`, preuves, snapshot) ; demande de dépendance ; claim canonique ; événements d'activité. Définir versionnement et adaptation aux modèles existants, sans refonte générale préalable.
- **Périmètre :** documentation d'architecture de remédiation ; revue de `models.py`, `runner.py`, `pipeline.py`, `delivery_gate.py`, `observability.py`. Écriture des interfaces communes sous verrou.
- **Validation :** une entrée/sortie d'exemple pour chaque interface ; erreurs et migrations d'état décrites ; pas de secret dans les événements ; chaque tâche suivante a un propriétaire de raccordement identifiable.

### REM-01 — Confinement réel de l'exécution

- **Constat :** une réparation a pu invoquer un arrêt global de Python sur l'hôte. Un prompt d'interdiction ne suffit pas.
- **Travail :** examiner le chemin réel Claude Code/provider/outils, choisir puis implémenter une frontière d'exécution qui empêche l'accès aux processus et fichiers des autres projets. Orchestrateur et secrets hors portée ; pas de socket Docker ni de privilèges hôte donnés au code généré. Vérifier la compatibilité avec l'authentification abonnement sans copier les credentials dans le projet/image.
- **Périmètre :** `agents/runner.py`, `agents/providers.py`, `orchestrator/sandbox.py` ; raccordement pipeline sous verrou. Ne pas confondre sandbox des tests et confinement du harness lui-même.
- **Validation :** dans un banc isolé avec processus/fichiers sentinelles, une tentative d'arrêt large ou d'écriture hors projet échoue sans affecter les sentinelles ni l'orchestrateur. Chemin nominal fonctionnel. Backend incapable de garantir l'isolation : refus explicite, pas de fallback silencieux sur l'hôte.

### REM-02 — Arrêts limités aux ressources possédées

- **Travail :** registre par run des handles/PID avec identité de création, enfants, conteneurs, ports et volumes. Arrêt gracieux puis forcé borné ; gestion des enfants détachés et PID réutilisés ; nettoyage idempotent. Remplacer les commandes larges de lancement/réparation par ces opérations.
- **Périmètre :** `runner.py`, `bootstrap.py`, `deploy.py`, `docker_deploy.py` ; `test_runner_processes.py`, `test_bootstrap_processes.py`.
- **Validation :** deux projets simultanés et une sentinelle : arrêt/retry/timeout de A ne modifie pas B ; PID obsolète refusé ; aucun arrêt par nom d'exécutable ; ressources non possédées conservées. Preuve d'exécution Windows, pas seulement mocks POSIX.

### REM-03 — État terminal durable et récupération

- **Constat :** après disparition du serveur, état persistant `build` et erreur vide.
- **Travail :** états séparés tâche/génération/livraison, identité du worker, journal atomique, détection de run interrompu au redémarrage et réconciliation. La détection ne doit pas dépendre uniquement d'un `finally` dans le processus tué. Reprise uniquement explicite, sans doubler tâches ou dépenses.
- **Périmètre :** `storage.py`, `delivery_state.py`, `build_monitor.py`, API ; `models.py` et pipeline sous verrou.
- **Validation :** arrêt brutal pendant appel, merge et smoke ; redémarrage montre « interrompu » avec dernier jalon, pas « succès ». Une tâche DONE n'implique jamais une livraison réussie. La réconciliation ne relance aucun LLM automatiquement.

### REM-04 — Dépendances déclarées et droit de modifier les manifests

- **Constat :** Argon2 installé seulement dans une venv, le manifest étant hors périmètre de la tâche.
- **Travail :** demande structurée d'ajout de dépendance avec propriétaire du manifest/lock, intégration sérialisée et attente explicite de la tâche consommatrice. Les claims ne doivent ni interdire sans issue une dépendance légitime, ni autoriser des modifications concurrentes du lock.
- **Périmètre :** `toolchain.py`, planification, prompts et pipeline sous verrou ; cas Python et Node adaptés aux stacks effectivement supportées.
- **Validation :** scénario Argon2 absent : demande → manifest+lock → installation propre → primitive réelle. Deux demandes concurrentes restent présentes dans le lock ; dépendance runtime ne finit pas seulement dans les dev dependencies ; absence de résolution empêche GREEN.

### REM-05 — Environnement propre avant validation

- **Travail :** reconstruire ou utiliser un cache attesté par les hashes manifest/lock/toolchain/plateforme. Séparer environnement agent, tests et runtime ; aucun paquet installé manuellement ne doit rendre une branche admissible. Préserver les caches immuables sûrs pour ne pas tout télécharger à chaque test.
- **Périmètre :** `toolchain.py`, `sandbox.py`, canaris et exécution de tests dans pipeline ; suites `test_toolchain.py`, `test_frontend_toolchain.py`.
- **Validation :** venv volontairement enrichie puis validation depuis lock incomplet : échec précis. Lock modifié invalide le cache. Branche propre et image passent avec mêmes dépendances runtime ; versions/hash de l'environnement dans les preuves.

### REM-06 — Intégrité des preuves de tests

- **Constat :** `importorskip` a masqué l'absence du hasher ; tests constitutionnels visant un module inexistant ignorés.
- **Travail :** baseline des tests critiques attendus, comptage collecte/exécution/skip/xfail, contrôle des suppressions et changements d'assertions lors d'une reprise. Exceptions justifiées et revues, sans interdire tous les skips légitimes de toutes les stacks. Les tests de contrat indépendants sont inaccessibles en écriture à l'agent produit.
- **Périmètre :** `constitution.py`, `delivery_gate.py`, parseurs de résultats et prompts sous verrou.
- **Validation :** zéro test, renommage cassant la collecte, suppression, `importorskip` critique et assertion affaiblie ne donnent pas GREEN. Cas de skip plateforme explicitement autorisé accepté. Régression Argon2 détectée sur environnement propre, même si la suite native sort avec code 0.

### REM-07 — Réparation diagnostiquée et bornée

- **Travail :** distinguer défaut dépendance, échec de contrat, environnement indisponible, conflit, timeout et erreur provider. Transmettre preuve et critères non négociables à la réparation ; plafond de tentatives et budget restant ; détecter la répétition du même défaut. Toutes les réparations utilisent REM-01/02/05/06.
- **Périmètre :** logique de retry/canari/runtime dans pipeline et `runtime_acceptance.py` ; prompts sous verrou.
- **Validation :** import manquant n'est pas « corrigé » par skip ; deux échecs identiques terminent proprement selon limite configurée ; coût réservé/comptabilisé cohérent, interruption signalée et preuves conservées. Aucun restart global ni boucle infinie.

### REM-08 — Stack explicite et structurée

- **Travail :** matérialiser la décision de pré-analyse : contraintes explicites prioritaires, backend/frontend/DB, raisons du choix, capacités de scaffold et versions. En absence de contrainte, préférences utilisateur Go/Rust ou Python pour backend, React pour front, sans les rendre obligatoires si le contexte justifie autre chose. Un choix LLM est persisté une fois ; bootstrap ne le réinterprète pas depuis la prose.
- **Périmètre :** `stack.py`, `bootstrap.py`, import/pré-analyse ; `test_project_foundation.py`. Conserver le patch « vue » existant.
- **Validation :** React + « vue client » reste React ; Vue explicitement demandé reste Vue ; contraintes contradictoires donnent décision/action explicite ; stack non supportée annoncée avant dépenses de build, sans substitution cachée. Ne pas implémenter toutes les stacks pour clore cette tâche.

### REM-09 — Contrat indépendant et traçable

- **Travail :** artefact versionné dérivé du brief : IDs, priorité B/M/D, rôles/routes, transitions, bornes, DTO, invariants, scénarios et preuves attendues ; conserver le texte source et ses hashes. Extraction LLM relue et validée avant gel, pas promesse de déterminisme du LLM. Les attentes ne sont pas recalculées à partir du code produit.
- **Périmètre :** `spec_import.py`, planification et nouvelle couche de contrat spécialisée à convenir en REM-00.
- **Validation :** exactement les 57 IDs de Relais Support retrouvés ; divergence d'un endpoint, d'une borne ou d'une transition détectée. Exemple minimal d'une autre application pour vérifier que le mécanisme n'est pas codé en dur pour le support. L'agent produit ne peut éditer l'oracle indépendant.

### REM-10 — Gate de plan plutôt que moyenne permissive

- **Constat :** score 84/100 et 13 findings ; critique persistée sans nouvelle décision. Un juge invalide peut retourner le seuil : défaut latent à reproduire.
- **Travail :** contrôler structure, couverture du contrat et contraintes avant admission ; findings graves confirmés nécessitent résolution ou arbitrage explicite. Définir « lot », maximum, fondation et jalon vertical dans le schéma du plan. Ne pas bloquer automatiquement sur chaque opinion du critique ni inventer des cycles absents du graphe.
- **Périmètre :** `refine.py`, `plan_pipeline.py`, pipeline et `test_refine.py`, `test_plan_pipeline.py`.
- **Validation :** score élevé avec invariant violé refusé ; score invalide/provider indisponible ne vaut pas succès ; finding réfuté avec preuve autorisé ; DAG réel vérifié ; max de lots respecté selon définition figée, pas selon un comptage ambigu après coup.

### REM-11 — Claims canoniques et contrats communs

- **Travail :** résoudre les claims par rapport à la racine réelle du socle, valider traversées/chemins absolus/casse/séparateurs, préserver les globs légitimes de fichiers futurs. Déclarer erreurs/horloge/DB et leurs propriétaires avant consommateurs ; manifests reliés à REM-04.
- **Périmètre :** plan, cartographie, `_file_in_scope` et admission dans pipeline ; tests de chemins Windows et POSIX.
- **Validation :** package racine `relais_support/` ne reçoit plus `backend/relais_support/` par erreur ; incohérence refusée avant worker. Cas DB important erreurs/horloge impose dépendance ou contrat partagé préexistant ; pas de faux hors-périmètre ni perte de fichier nécessaire.

### REM-12 — Collision lors de l'élargissement d'un claim

- **Travail :** arbitrage central d'un élargissement vers un propriétaire actif : attente, transfert ou intégration sérialisée explicite. Tests déterministes du scheduler ; nombre de retries borné et motif observable. Une détection après merge n'est pas la seule défense.
- **Périmètre :** `arbitration.py`, ordonnancement et scope enforcement dans pipeline.
- **Validation :** deux workers synchronisés réclament `clock.py`/`errors.py` : un propriétaire d'écriture à la fois, aucun deadlock ; tâche refusée/replanifiée proprement, aucun retrait aveugle de dépendance ; reprise ne perd pas les changements déjà intégrés.

### REM-13 — Fondation déterministe testée immédiatement

- **Travail :** auditer et durcir les templates existants avant d'en créer d'autres. Pour chaque stack prise en charge : arborescence versionnée, manifests/locks, configuration, migrations, endpoint minimal, front minimal et proxy relatif `/api`. Initialisation et rejeu idempotents ; diagnostic explicite des prérequis.
- **Périmètre :** `bootstrap.py`, `stack.py`, `docker_deploy.py` et ressources de templates réellement référencées ; `test_project_foundation.py`, `test_bootstrap_docker.py`.
- **Validation :** création depuis dossier propre → installation → lancement → HTTP API → accès DB → navigateur front appelant réellement API ; échec à chaque maillon bloque la suite. Rejeu ne détruit aucune donnée ni source existante. Test du cas sans DB et refus des stacks hors capacités.

### REM-14 — Jalon vertical avant expansion métier

- **Constat :** React monté et SELECT 1 validaient le socle, mais le login cassé n'a été détecté qu'après 27 tâches.
- **Travail :** distinguer sonde de fondation et première tranche métier. Pour une application authentifiée, ordonner migration → bootstrap explicite → hash réel → login navigateur → création/lecture d'un objet via API/DB. Le plan ne libère les fonctionnalités suivantes qu'après ce jalon ; adaptateur sans auth pour les briefs concernés.
- **Périmètre :** `runtime_acceptance.py`, jalons de plan et gate pipeline ; test du cas Argon2 et fixture frontend/backend réelle.
- **Validation :** Argon2 manquant échoue avant les tâches métier aval ; fixture corrigée passe sans session injectée ni auth mockée. Délai maximum et nettoyage bornés ; journaux sans secrets. Un healthcheck seul ne valide jamais la tranche.

### REM-15 — Contrats sécurité et comptes

- **Cible de régression :** SEC-01 à SEC-15 ; neuf échecs, cinq preuves manquantes et un PASS à préserver.
- **Travail :** transformer les probes en pack indépendant et en exigences transmises aux agents : bootstrap/rejeu, unicité concurrente, vrai Argon2, limiter, cookies HTTPS/exception locale, révocation/réactivation, CSRF y compris logout, rôles/IDOR, notes internes, mass assignment, XSS, dernier admin, logs et no-store y compris 500.
- **Périmètre :** pack de tests de contrat isolé ; règles de génération/prompts sous verrou. Aucun edit du snapshot. Ne pas classer une route manquante 405 comme une fuite de données démontrée.
- **Validation :** fixtures bonnes/mauvaises pour chaque famille ; DB avant/après refus ; reproduction de l'absence de Secure et de logout sans CSRF ; parcours réel des comptes sans remplacer le service de sécurité. Le contrôle de notes/XSS dans le navigateur est raccordé à REM-19.

### REM-16 — Contrats métier et concurrence

- **Cible :** FUN-01 à FUN-13. Les règles exactes restent celles du brief, pas celles inventées par les tests générés.
- **Travail :** matrices rôles/création, bornes, priorité/assignation, transitions 4×4 et préconditions, messages, CAS, audit, désactivation/réactivation, recherche littérale, filtres ET, pagination, dashboard et no-op. Rejouer idempotence après restart et permissions avant replay.
- **Périmètre :** pack de contrats métier, fixtures et adaptateur API ; attentes séparées de l'implémentation du produit.
- **Validation :** fixtures fautives acceptant open→resolved, agent créateur ou filtres ignorés échouent ; courses sur connexions distinctes vérifiées en DB ; rollback total et pas de doublons. Les anciens PASS restent dans la suite. Brouillons/rafraîchissement UI transmis à REM-18/19, pas présumés validés par HTTP.

### REM-17 — Contrats DB/API/frontend

- **Cible :** ARC-01 à ARC-09 ; échecs ARC-02/06/07, autres acquis à préserver.
- **Travail :** vérifier contraintes SQL directes, nullité des IDs et types des versions ; migrations sans perte ; concurrence/verrous ; nombre de requêtes ; OpenAPI/routes et DTO réels ; schéma d'erreur commun et mapping `display_name` ; pagination/tri de toutes les listes ; UTC et organisation frontend motivée.
- **Périmètre :** pack architecture, tests d'intégration des contrats client/serveur, règles de templates si cause générique confirmée.
- **Validation :** SQLite refuse ID NULL et version fractionnaire ; client consomme réellement l'erreur renvoyée par API ; GET/PATCH users exigés existent ; listes bornées et tris contractuels. Comparer lignes/hashes pour migrations, non seulement compteurs. Ne pas confondre conversion PowerShell locale et erreur UTC produit.

### REM-18 — Contrats UX, session et réseau

- **Cible :** UX-01 à UX-08 ; FAIL UX-01/02/03/05, autres non vérifiés.
- **Travail :** parcours/navigation par rôle ; chargement/vide/erreur ; état « résultat incertain » conservant payload+UUID jusqu'au rejeu ; expiration 401 réellement câblée et purge de cache/brouillons ; conflits sans écrasement ; clavier/modales/erreurs associées ; mobile/texte long ; recherche à réponses inversées ; distinction public/interne.
- **Périmètre :** pack navigateur et règles frontend transmises au générateur, pas une réparation locale de ses composants.
- **Validation :** fixtures avec callback 401 non raccordé et UUID changé après timeout sont détectées ; tests réels desktop/mobile/clavier ; Alice→logout→Bob sans contenu antérieur ; champs d'erreur annoncés et brouillon conservé sur 409. Tests unitaires mockés seuls insuffisants.

### REM-19 — Tests complets et E2E reproductibles

- **Cible :** TST-01 à TST-06 ; compléter également toutes les preuves navigateur manquantes SEC/FUN/UX.
- **Travail :** manifests incluant outils de test/coverage/E2E ; mapping réel requirement→tests/assertions ; six parcours exacts du §8 du brief, fixtures indépendantes et base isolée. Mesurer couverture avec fichiers non exécutés et conserver numérateurs/dénominateurs. Mutation d'autorisation seulement dans copie identifiée.
- **Périmètre :** infrastructure de validation, pack indépendant et générateur de scripts de test ; intégration REM-06 et REM-15..18.
- **Validation :** commande propre par suite ; chaque parcours lancé seul puis ensemble ; absence de mocks nominaux du backend/auth ; console et captures conservées. Seuils du référentiel respectés sans exclusions métier. Dépendance manquante, zéro collecte ou skip critique donnent échec. Mutation détectée, original inchangé.

### REM-20 — Livraison Docker, persistance et README

- **Cible :** OPS-01 à OPS-06, dont persistance nominale encore non vérifiée.
- **Travail :** refaire les parcours sur l'image finale exacte, non une venv hôte ; créer ticket/réponse/note, recréer conteneur avec même volume et vérifier données/audit/idempotence. README exécuté sur installation propre, clés de seed explicites, commandes de suite/couverture/E2E/migration/sauvegarde correctes. Audit daté et arbitrage d'exploitabilité.
- **Périmètre :** `docker_deploy.py`, `delivery_gate.py`, templates de livraison/doc et tests isolés.
- **Validation :** image non-root/loopback, volume inscriptible, aucune copie de secrets/DB/venv ; bootstrap/login nominal réels ; undeploy conserve volume ; sauvegarde vise le bon nom Compose. Audit indisponible → preuve manquante, pas succès ; avis de dev tooling ≠ exploitation production présumée. Mesurer durées sans retirer de scénarios.

### REM-21 — Gate finale et rapport indépendants

- **Travail :** agréger tests natifs, contrats externes, revue et navigateur sur une même identité d'artefact ; invalider les preuves après changement de code pertinent. 57 IDs exacts pour ce benchmark ; modèle générique pour un autre contrat. Séparer tâches terminées, app déployée et verdict d'acceptance.
- **Périmètre :** `delivery_gate.py`, `delivery_state.py`, API/UI de livraison et raccordements pipeline sous verrou.
- **Validation :** 27 tâches DONE + login500 => livraison refusée ; PASS sans preuve requise rejeté ; ID manquant/doublon/hash obsolète détecté. Rapport attendu/observé/repro/preuves/impact/limites ; B/M obligatoires, aucun score compensatoire. NOT_VERIFIED reste distinct de FAIL ; contrôle parent des PASS bloquants.

### REM-22 — Activité et coût réellement observables

- **Constat :** plafond budgétaire sérialisant intentionnellement les LLM, tandis que plusieurs workers sont affichés running.
- **Travail :** exposer attente budget/verrou/dépendance, appel provider actif, tests, merge, réparation ; dates/durées/occupant et dernier progrès. Distinguer estimation, consommation enregistrée, réserve et appel interrompu non encore comptabilisé. Ne pas promettre un coût facturé à partir d'un compteur estimé.
- **Périmètre :** `observability.py`, `metrics.py`, tracker pipeline ; `Activity.tsx`, `LlmActivity.tsx`, types et traductions sous verrou.
- **Validation :** deux workers dont un attend : affichage non ambigu et timers cohérents ; événements out-of-order/reconnexion sans faux progrès ; cap conservé ; scénario interruption marque coût incomplet. Aucun secret ni payload privé publié dans la télémétrie.

### REM-23 — Parallélisme budgétaire, option après mesures

- **Travail :** mesurer d'abord le temps réellement perdu. Si justifié, réserver atomiquement une allowance bornée par appel, libérer/rapprocher les consommations et gérer crash/annulation. Si provider incapable de borner un appel, conserver la sérialisation et documenter la limite.
- **Périmètre :** tracker de budget et `test_usage_budget_hardening.py`, `test_wave1_requeue_budget.py`.
- **Validation :** courses de réservation, timeout, résultat tardif et retry : jamais deux allocations du même solde ; consommation enregistrée + réserves ≤ plafond applicable. Aucun relèvement de cap ni retrait de protection. Mesures avant/après ; gain nul autorise à différer l'optimisation, pas à inventer une réussite.

### REM-24 — Contre-revue intégrée avant nouveau run

- **Travail :** vérifier les tâches intégrées sur une révision commune ; tests unitaires et intégration de la fabrique, bancs isolés, contrats API/UI et scénarios adverses. Relire limites d'isolation, faux verts et transitions d'état. Rejouer les anciens PASS du produit sur les fixtures des packs et vérifier l'oracle sur plusieurs exemples.
- **Périmètre :** coordination et preuves ; tout correctif retourne vers sa tâche propriétaire.
- **Validation :** toutes P0/P1 REM-00..22 DONE ; état Git/diffs et révision identifiés ; pas de dépendance injectée hors lock ; aucun accès aux autres projets pendant les essais ; revue critique indépendante approuvée. Cette étape ne constitue pas encore une nouvelle génération Relais Support réussie.

### REM-25 — Nouvelle génération, puis évaluation indépendante

- **Prérequis externe :** reconfirmer avant lancement le provider, modèle, authentification abonnement, plafond et autorisation pour la nouvelle campagne. Les 40 USD étaient autorisés pour la campagne historique ; ne pas les réutiliser implicitement. Aucun crédit additionnel ni API directe activés.
- **Travail :** nouveau dossier/run, même brief v0.2 et hashes ; aucune réparation manuelle du résultat entre génération et verdict. Mesurer jalon fondation, tranche verticale, durée, retries/collisions et usage réellement rapporté. Après arrêt, snapshot et revue indépendante par sous-agents GPT-6.1 Sol medium selon la demande initiale.
- **Validation :** les 57 critères sont réévalués, y compris les 17 anciens PASS ; 13 NOT_VERIFIED explicitement repris. JSON/Markdown complets et comparaison avant/après (statuts, preuves, durée, coût estimé et appels manquants). Tous les 56 B/M doivent être PASS pour déclarer la cible conforme ; OPS-06 séparé. Si échec, rapport livré et nouvelles tâches documentées, jamais auto-déclaration de succès ni boucle payante illimitée.

## 5. Traçabilité des constats et des critères

### Défauts de fabrique → tâches

| Constat | Source | Tâches responsables |
|---|---|---|
| Arrêt global des processus ; orchestrateur disparu | Incident terminal | REM-01, REM-02, REM-03, REM-07 |
| Dépendance installée seulement en venv et manifest hors claims | Analyse §7 | REM-04, REM-05, REM-11 |
| Skip critique utilisé à la place d'une correction | Analyse §7, TST-01 | REM-06, REM-07, REM-19 |
| Socle vert mais login 500 détecté en fin de construction | Incident, OPS-03 | REM-13, REM-14, REM-21 |
| Stack mal reconnue depuis la prose, correction Vue déjà faite | Analyse §1 | REM-08 |
| Score du plan suffisant malgré findings, juge permissif latent | Analyse §2 et §6 | REM-09, REM-10 |
| Racines de claims erronées et dépendances communes absentes | Analyse §3–4 | REM-00, REM-11, REM-12 |
| Contrats générés différents du brief | Rapport FUN/ARC/TST | REM-09, REM-15, REM-16, REM-17, REM-18, REM-21 |
| Attentes budget invisibles, ralentissement non isolé | Analyse §5 | REM-22 ; REM-23 seulement si justifié |
| Nombre de tâches terminées confondu avec état de livraison | Rapport global | REM-03, REM-21, REM-24, REM-25 |

### Couverture des 57 critères produit

Le responsable primaire conçoit les contrôles ; REM-19 les exécute en chaîne, REM-21 contrôle les preuves, REM-25 requalifie une nouvelle sortie. Un critère multi-couches ne passe pas par addition d'hypothèses entre agents.

| Responsable primaire | IDs FAIL de référence | IDs NOT_VERIFIED de référence | IDs PASS à préserver |
|---|---|---|---|
| REM-15 | SEC-01, SEC-03, SEC-04, SEC-05, SEC-06, SEC-07, SEC-08, SEC-13, SEC-15 | SEC-02, SEC-10, SEC-11, SEC-12, SEC-14 | SEC-09 |
| REM-16 | FUN-01, FUN-03, FUN-04, FUN-09, FUN-11 | FUN-02, FUN-06, FUN-12 | FUN-05, FUN-07, FUN-08, FUN-10, FUN-13 |
| REM-17 | ARC-02, ARC-06, ARC-07 | — | ARC-01, ARC-03, ARC-04, ARC-05, ARC-08, ARC-09 |
| REM-18 | UX-01, UX-02, UX-03, UX-05 | UX-04, UX-06, UX-07, UX-08 | — |
| REM-19 | TST-01, TST-02, TST-03, TST-05 | — | TST-04, TST-06 |
| REM-20 | OPS-03, OPS-05 | OPS-04 | OPS-01, OPS-02, OPS-06 (diagnostic) |

Points d'interface obligatoires : SEC-10/12 et FUN-02/06/12 nécessitent le navigateur de REM-18/19 ; UX-05 exige la vraie révocation/session de REM-15 ; OPS-04 exige objets/audit/idempotence de REM-16. Les responsables ne s'attribuent pas un PASS complet sur leur seule couche.

## 6. Modèle de délégation et de remise

À copier dans une mission d'agent après attribution par le coordinateur :

```text
Mission : REM-XX — <titre>
Objectif : <résultat testable de la fiche>
Base de travail : <révision et changements préexistants à préserver>
Dépendances DONE : <IDs et preuves>
Périmètre exclusif : <fichiers/modules/tests>
Verrous partagés détenus : <liste, ou aucun>
Interdits : snapshot historique, autres projets/DB, arrêt global,
            modification de l'oracle pour rendre le test vert, appel payant non autorisé.
Interfaces à respecter : <contrats validés REM-00 et propriétaires voisins>
Critères : <copie exacte de la validation de la fiche>
Tests : <contre-exemple, nominal, négatifs, non-régressions>
Artefacts : artifacts/remediation/REM-XX/<run-id>/
Remise : résumé, fichiers changés, commandes/codes retour, preuves,
         limites, conflits/élargissements demandés, révision à intégrer.
Ne pas modifier le tableau partagé. Demander REVIEW ; ne pas s'attribuer DONE.
```

Le coordinateur vérifie l'intégration, assigne un relecteur, puis met à jour le tableau et le journal. En cas de blocage : préciser fait observé, alternatives tentées, propriétaire de la décision et condition exacte de reprise.

## 7. Journal des décisions

| Date | Tâche | Décision / changement | Responsable | Preuve |
|---|---|---|---|---|
| 2026-10-09 | Toutes | Backlog initial préparé ; aucune implémentation ni nouvelle génération lancée | Coordinateur | Rapports de campagne référencés en §1 |
| 2026-10-11 | REM-00 | Démarrage autorisé par l'utilisateur ; interfaces minimales gelées, propriété des fichiers partagés au coordinateur, snapshot de travail dans worktree d'intégration | Coordinateur | 04_interfaces_remediation.md |

## 8. Condition de clôture du programme

Le programme n'est pas clos parce que ce tableau est rempli ou que les suites unitaires sont vertes. Il faut une fabrique confinée, une révision intégrée vérifiée, puis une nouvelle sortie évaluée indépendamment et **56/56 critères obligatoires PASS**, avec preuves complètes et ressources utilisateur préservées. La remédiation facultative REM-23 peut rester différée explicitement. Toute évolution du brief ou du référentiel crée une version distincte et interdit une comparaison silencieuse avec la baseline v0.2.
