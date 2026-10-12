# Autospec — backlog de fiabilisation après Relais Support

Version 1.7 — fabrique qualifiée le 12 octobre 2026 ; REM-25 en cours, défaut du payload corrigé et reprise pré-bootstrap qualifiée, génération réelle restant à poursuivre. Document de travail pour un coordinateur et des agents parallèles.

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
| TODO | Non commencé ; l'éligibilité dépend du graphe | IN_PROGRESS après attribution ; préparation indépendante permise, intégration/libération soumise aux dépendances DONE |
| IN_PROGRESS | Un propriétaire, un périmètre et une base de travail identifiés ; préparation de module ≠ raccord complet | REVIEW après raccord et dépendances DONE, ou BLOCKED |
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
| REM-01 | P0 | Confinement réel des agents | Exécution | REM-00 | DONE | rem_execution + coordinateur | Docker NETNONE, broker et navigateur isolés ; launcher pytest image-owned 9744192a, parent 53 PASS natifs ; garde API Origin/Host ffc8e5ca, TCP réel et 104 PASS ; globale finale 7b1ea54c : 3 232 PASS, 100 SKIP, 0 FAIL/ERROR |
| REM-02 | P0 | Cycle de vie des processus possédés | Exécution | REM-01 | DONE | rem_execution + coordinateur | f43ba62c, b32d9f55 : handles/Jobs Windows, CID exact créé par l'appel, drainage des workers annulés, intention stopping durable, deux journaux avant DELETE ; 58 PASS natifs et contre-revue a79ce3b9 : 19 PASS |
| REM-03 | P0 | État durable et récupération après interruption | Orchestration | REM-02 | DONE | Coordinateur + rem_contracts_plan | 3a5d4a78/73eef96a : opérations provider/merge/smoke effectives + arrêt réel/restart, parent 4 PASS/42,62 s ; coût inconnu bloque redispatch ; preuves REM-03/20261012-parent-effective-operations ; globale commune verte, voir REM-24/20261012-final-qualification |
| REM-04 | P0 | Dépendances et manifests dans le workflow | Reproductibilité | REM-00 | DONE | rem_dependencies + coordinateur | c3701d17 et raccord _aresolve_dependency au broker sérialisé ; Argon2 réel, 86 tests ; require_ready empêche GREEN sans résolution ; matrice DoD indépendante confirme le raccord |
| REM-05 | P0 | Validation dans un environnement propre | Reproductibilité | REM-04 | DONE | rem_dependencies + rem_execution + coordinateur | Lock Linux, cache attesté, atomic Windows c1e21400 ; Python root explicite ; Vitest 4.1.11/provider et Vite 6.4.4 natifs ; parent publication/atomic 37 PASS ; globale quatrième 3 044 PASS/10 FAIL/93 SKIP conservée, cinquième 7b1ea54c : 3 232 PASS/100 SKIP/0 FAIL/ERROR |
| REM-06 | P0 | Interdire les preuves de tests affaiblies | Qualité | REM-05 | DONE | rem_execution + coordinateur | Baselines, hashes et QA externe raccordés ; faux rapport via pytest.py réellement reproduit puis fermé par 9744192a ; collecte/coverage/asyncio trusted, parent 53 PASS natifs ; aucun reporter/score producteur ne vaut acceptation |
| REM-07 | P0 | Réparations bornées et classifiées | Orchestration | REM-03, REM-06 | DONE | Coordinateur | eec74191/a247e332 ; délai réel/répétition/rollback et canaris _apost_merge_canary raccordés ; corpus mécanique 182 PASS ; coût inconnu demeure bloquant, FakeRunner inert seul reçoit zéro coût attesté |
| REM-08 | P1 | Décision de stack structurée | Fondation | REM-00 | DONE | Coordinateur | 199 tests stack/fondation, a247e332 ; reprise scellée et contradictions |
| REM-09 | P1 | Contrat exécutable indépendant du code produit | Contrats | REM-00 | DONE | rem_contracts_plan + coordinateur | Sources v0.2 immuables/57 IDs importées et scellées hors produit ; quatre faits source-only parent relus, 15 ancres exactes ; réponses GPT liées au request_hash/phase/snapshot, aucun export de revue à Claude |
| REM-10 | P1 | Admission du plan par contraintes et findings | Planification | REM-08, REM-09 | DONE | rem_contracts_plan + coordinateur | DAG, 7 lots source-scellés et stack structurée ; source_plan_limits validé avant persist/provider ; 68 PASS API/plan, score invalide jamais seuil par défaut |
| REM-11 | P1 | Claims normalisés et dépendances communes | Planification | REM-04, REM-10 | DONE | rem_contracts_plan + coordinateur | Racines/globs et contrats communs raccordés ; overlap wildcard premier segment corrigé ; contre-revue claims 45 PASS, aucune autorisation par simple nom de fichier |
| REM-12 | P1 | Conflits dynamiques de propriété des fichiers | Ordonnancement | REM-11 | DONE | rem_contracts_plan + coordinateur | Arbiter de claims pré-écriture, attentes/dépendances/remediation bornées raccordées ; sérialisation et crash d'un worker contrôlés ; contre-revue claims 45 PASS |
| REM-13 | P0 | Socle déterministe et sondes initiales | Fondation | REM-05, REM-08 | DONE | rem_execution + coordinateur | Python/React/nonce same-origin en Docker NETNONE qualifiés ; CMD/browser parent 27 PASS et faux bootstrap 3 PASS ; globale verte |
| REM-14 | P0 | Première tranche métier réellement fonctionnelle | Acceptation | REM-06, REM-09, REM-13 | DONE | rem_dependencies + coordinateur | 2f600d0b/6644e03d : jalon bloquant raccordé ; Argon2/login/API/DB/restart et browser NETNONE ; parent transport/CMD 27 PASS ; qualification de capacité, jamais 57 PASS produit |
| REM-15 | P1 | Pack de contrats sécurité et comptes | Contrats sécurité | REM-09 | DONE | rem_dependencies + rem_contracts_plan + coordinateur | 240f7049/0f57aadb/7b1ea54c : scans natifs complets et TLS/HTTP/CSRF/logs child ; agent brut 30 PASS, parent classifié 30 PASS/245,137 s et unités 100 PASS/7 SKIP ; dix empreintes PEM/DER source exactes/candidats conservés/négatif garde deux findings ; addendum indépendant ferme régression, globale commune verte, voir REM-24/20261012-final-qualification |
| REM-16 | P1 | Pack de contrats métier et concurrence | Contrats métier | REM-09 | DONE | rem_dependencies + coordinateur | FUN réels raccordés : API/SQLite distinctes, CAS, idempotence et rollback ; 9 métatests natifs/138 preuves initiales conservés ; aucun PASS du futur produit déduit |
| REM-17 | P1 | Pack DB, API et cohérence frontend/backend | Contrats architecture | REM-09 | DONE | rem_dependencies + rem_contracts_plan + coordinateur | ARC SQLtrace/rollback/horloge/CAS Linux ; ARC-06 client DTO/display_name + erreur HTTP réelle raccordé 8023168a après f72f15e6 ; parent Docker NETNONE 1 PASS/26,39 s ; aucun nominal injecté ni PASS ARC complet déduit |
| REM-18 | P1 | Pack UX, session et erreurs réseau | Contrats frontend | REM-09 | DONE | rem_contracts_plan + coordinateur | DockerBrowserSession NETNONE, origin allowlist exacte, service workers/WS/redirect contrôlés ; preuves visuelles/natives séparées ; tests navigateur et restart qualifiés, aucun Chromium hôte nominal accepté |
| REM-19 | P1 | Suites complètes, couverture et six E2E | Qualité | REM-14, REM-15, REM-16, REM-17, REM-18 | DONE | rem_execution + rem_contracts_plan + coordinateur | 78eac077/015c66b9 : collecte native automatique, argv/rc réels, vrais hashes/kill X mutant, 12 E2E source scellés réutilisables ; 89 PASS dont Linux réel ; raccord final root 1c145f99 |
| REM-20 | P1 | Image finale, persistance et documentation | Livraison | REM-14, REM-19 | DONE | rem_dependencies + rem_execution + coordinateur | CMD baked identique au commandement revu, migration avant app sans seed implicite, image immuable sans rebuild ; packages UUID distincts des images partagées ; 47/58 PASS natifs et parent 37 PASS publication/atomic ; README/audits/horloges source-reviewés |
| REM-21 | P1 | Gate finale indépendante et traçabilité | Acceptation | REM-19, REM-20 | DONE | Coordinateur | b32d9f55/a79ce3b9 : cache moteur/seals/report SHA, revue fresh avant cache, image actuelle même delivery OFF ; 4 contre-tests + parent 95 PASS ; 8023168a : raccord natif/UI/fresh conservateur, indépendant 22 PASS puis mêmes 22 PASS parent ; aucun premier FAIL/incomplet promu |
| REM-22 | P1 | Télémétrie des attentes, coûts et phases | Observabilité | REM-00 | DONE | Coordinateur | Tours provider distincts des outils/attentes ; 72 tests ciblés, UI 3 tests/build PASS |
| REM-23 | P2 | Réservation budgétaire concurrente, optionnelle | Optimisation | REM-07, REM-22 | DONE | rem_execution + coordinateur | faf58c25 : reçu payé préservé même si cleanup claims annulé/échoué, OFF et concurrent ; 76 PASS ; OFF pour Claude faute de cap financier dur qualifié |
| REM-24 | P1 | Contre-revue intégrée de la fabrique | Intégration | Toutes P0/P1 REM-00 à REM-22 | DONE | Trois agents + coordinateur | Snapshot propre 7b1ea54c ; cinquième globale 3 232 PASS/100 SKIP/0 FAIL/ERROR, 29 min 47 s ; frontend 308 PASS/build PASS ; probes et contre-revues critiques séparées ; décision finale et limites dans REM-24/20261012-final-qualification/README.md ; aucun PASS produit déduit |
| REM-25 | P1 | Nouvelle campagne et comparaison indépendante | Qualification | REM-24 + autorisation de lancement | IN_PROGRESS | Coordinateur + rem_dependencies + relecteur indépendant | Campagne unique à 312cc2d3, projet 0e6ebc49 ; erreur initiale de labels avant LLM conservée. Lanceur corrigé/intégré 5d30ac82 : auteur 129 PASS, contre-revue 145 PASS, parent 344 PASS/0 SKIP ; superviseur/API PUT/cleanup réels sur copie rc0, resume intercepté/zéro LLM, original intact ; REM-25/20261012-bootstrap-recovery-parent. Reprise réelle unique et 57 critères restent requis, aucun produit conforme annoncé |

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

- **Autorisation de lancement :** la demande explicite du 11 octobre d'exécuter les 26 tâches jusqu'à validation inclut cette nouvelle campagne. Conserver Claude Code connecté via abonnement claude.ai Team, modèle Sonnet, plafond conservateur de 40 USD estimés pour ce nouveau run ; vérifier ces paramètres avant lancement. Aucun crédit additionnel ni API directe activés. Un changement de provider, d'authentification ou une hausse du plafond demande une nouvelle autorisation.
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
| 2026-10-11 | REM-01..13 | Trois lots préparatoires mergés ; modules testés ≠ tâches closes tant que les raccordements réels ne sont pas vérifiés | Coordinateur | b648511c, c3701d17, ff6c372c ; artefacts par ID |
| 2026-10-11 | REM-03, REM-07, REM-08 | Cinq défauts de contre-revue corrigés : coût incomplet au restart, phase GOVERN, conflit stack, délai réel, environnement non réparable | Coordinateur | a247e332 ; 63 tests ciblés PASS dans environnement verrouillé |
| 2026-10-12 | REM-09..12, REM-21..22 | Import immuable API, admission du plan, claims avant écriture et admission des preuves raccordés/préparés ; attentes de médiation distinctes du provider | Coordinateur | 72 tests ciblés PASS ; JUnit root-raccord.xml ; modules seuls ne valent pas clôture |
| 2026-10-12 | REM-14, REM-19, REM-21 | L’utilisateur refuse les appels de revue des sources via Claude Code : génération seule dans Claude ; proposition opérationnelle puis revue indépendante dans deux sous-agents GPT 6.1 sol medium. Paquets locaux, snapshot exact, attente bornée/interrompable et aucune preuve X/V fabriquée | Coordinateur | tests/test_source_reviewer.py ; 28 tests locaux revue/budget PASS ; raccord attente en vérification |
| 2026-10-12 | REM-23 | Option concurrente testée mais OFF pour Claude : aucun cap financier dur qualifié. Journal durable reste bloquant après restart, changement de provider ou désactivation de l’option ; revue du raccord par rem_execution | Coordinateur | e0fe824c ; tests/test_budget_tracker_reservations.py ; contre-revue du 12 octobre |
| 2026-10-12 | REM-01, REM-06, REM-19, REM-23, REM-24 | Git local ne peut plus hériter de hooks/filtres/config globale ; cleanup borné et codes retour vérifiés ; vrais fichiers collectés protégés ; coût connu conservé après interruption ; plan qualité et profils mutation scellés par revue GPT externe distincte | Coordinateur | 68c963e0, 165deea8, 955f38ef ; README et JUnit review-boundaries ; dernier full replay lancé, pas encore de nouvelle génération |
| 2026-10-12 | REM-06, REM-19, REM-20, REM-21 | Baselines refusées jamais publiées ; registre QA authentifié conservateur et atomique, hashes réels au passage natif ; suite/couverture/mutation/E2E collectés avant jugement ; docs et advisory audits indépendamment revus ; réponse GPT liée au paquet exact et à sa phase | Coordinateur | 16c0e4ce, 78eac077, 015c66b9, 3296c96a, 1c145f99 ; 136 PASS/1 SKIP au raccord, preuves intermédiaires d'échec conservées |
| 2026-10-12 | REM-20, REM-22, REM-23 | Horloges installation/tests/browser/build/docker fondées sur opérations réelles séparées ; caches/layers gardent rc=None ; coût payé connu compté avant cleanup interruptible ; aucune activation de crédit ni appel LLM de revue | Coordinateur | ed617f08, 6abf48b4, faf58c25 ; 16 PASS horloges réelles et 76 PASS budget/cleanup |
| 2026-10-12 | REM-01, REM-20, REM-24 | Défauts réels de contre-revue à corriger : commandes Git internes locales merge-base/revert refusées ; navigateur HTTP seul insuffisant face à UDP/WebRTC ; image pouvant être testée avec un override différent du CMD livré. Image construite après revue d'argv exact, audit natif avant revue, pas de correction de produit pendant vérification | Coordinateur | 14 FAIL globale conservés ; corrections confiées à rem_dependencies, rem_contracts_plan et rem_execution ; REM-25 non lancé |
| 2026-10-12 | REM-03, REM-16..18, REM-21 | Raccords tardifs contrôlés : vrai crash CLI/Git/smoke/restart 4/4 ; contributions natives/UI/fresh sur cinq IDs, R-only ARC-01/09 et ARC-06 client réel Docker ; chemins UUID préservent les premiers X. Les métatests ne qualifient pas le futur produit | Coordinateur | REM-03 parent 4 PASS ; 8023168a, indépendant 22 PASS puis parent 22 PASS ; ARC-06 parent 1 PASS/26,39 s |
| 2026-10-12 | REM-15, REM-24 | Scan natif complet ajouté. Candidats PEM GnuTLS examinés sur sources primaires exactes : classification publique limitée par type/chemin/hash binaire/hash PEM, jamais exclusion vendor ni R fabriquée. Contre-revue découvre quatre PEM inline omis ; regex corrigée et logs mode TLS/CSRF capturés avant fermeture. Les rouges sont conservés | Coordinateur | 240f7049/0f57aadb/7b1ea54c ; raw v4 dix PEM/DER source exacts ; agent 30 PASS natifs ; parent 100 PASS/7 SKIP ; replay parent Docker final en cours |
| 2026-10-12 | REM-24, REM-25 | Quatrième globale 3 044 PASS/10 FAIL/93 SKIP conservée ; sept fixtures Host migrées à loopback et FakeRunner inert reçoit zéro usage attesté, coût inconnu réel toujours bloquant. Cinquième globale lancée sur 7b1ea54c propre. Launcher audité avec 51 PASS offline ; préflight/auth/inférence non effectués | Coordinateur | REM-24/20261012-final-integration/FOURTH-REGRESSION.md ; 1ab282e2, 0f57aadb ; aucun lancement REM-25 |

| 2026-10-12 | REM-00..24 | Qualification intégrée libérée dans l'ordre des dépendances : capacités REM-00..23 DONE, REM-23 reste OFF pour Claude faute de cap financier dur qualifié ; REM-24 DONE. Snapshot source propre 7b1ea54c, globale finale 3 232 PASS/100 SKIP/0 FAIL/ERROR, 3 warnings, 1 787,44 s ; frontend 308 PASS/build PASS ; raccords sécurité et ARC-06 natifs parent achevés et contre-revus. Les rouges historiques et skips demeurent conservés. REM-25 non exécuté à cette décision ; nouveau préflight frais, génération unique et 57 critères restent requis | Coordinateur | REM-24/20261012-final-qualification/README.md et FINAL-INTEGRATION-REVIEW.md ; REM-15 parent 30 PASS/0 SKIP ; REM-17 parent 1 PASS/0 SKIP ; REM-25 préflight Team puis superviseur intercepté avant POST, rc0 |

| 2026-10-12 | REM-25 | Premier POST unique sur 312cc2d3 : arrêt pré-LLM `Python/FastAPI` non canonique. Aucun code généré/appel/coût enregistré, préflight Team valide. Test de composition réel 1 FAIL/1 PASS ; récupération via API language/reprise démontrée sur fixture seulement. Correctif étroit du lanceur et garde de reprise confiés à rem_dependencies, revue indépendante requise ; pas de seconde création, reset de budget ni réparation produit | Coordinateur | REM-25/20261012-launch-stack-incident/README.md, état/monitor/préflight et JUnit rouge |

| 2026-10-12 | REM-25 | Payload canonique et continuation unique liés à l'incident exact, état/usage/oracle immuables et UNKNOWN durable. Contre-revue ferme attente de persist asynchrone, monitor inconnu et RPC contradictoire. Probe natif révèle stage/verrou de publication créés au startup ; allowance exacte après readiness seulement, admission initiale inchangée. Intégration 5d30ac82 : parent 344 PASS/0 SKIP, indépendant 145 PASS ; nouvelle copie natif rc0 avec vrai GET/PUT, resume intercepté avant transport, coût0, original intact et listener fermé. Gates du lanceur libérés, préflight frais et unique reprise réelle encore nécessaires ; backend/frontend de la globale 7b1ea54c inchangés | Coordinateur | REM-25/20261012-bootstrap-recovery-parent/README.md ; rouges historiques et native v1 conservés, aucune conformité produit déduite |

## 8. Condition de clôture du programme

Le programme n'est pas clos parce que ce tableau est rempli ou que les suites unitaires sont vertes. Il faut une fabrique confinée, une révision intégrée vérifiée, puis une nouvelle sortie évaluée indépendamment et **56/56 critères obligatoires PASS**, avec preuves complètes et ressources utilisateur préservées. La remédiation facultative REM-23 peut rester différée explicitement. Toute évolution du brief ou du référentiel crée une version distincte et interdit une comparaison silencieuse avec la baseline v0.2.
