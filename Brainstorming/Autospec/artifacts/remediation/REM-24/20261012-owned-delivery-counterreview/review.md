# Contre-revue indépendante — publication possédée et DoD

12 octobre 2026. Relecteur : `/root/rem_contracts_plan`. Cible lue seulement : worktree `autospec-remediation-integration`. Point de départ observé : `c0347674`, puis `047885d6` avec changements parent explicitement en cours dans API/pipeline/tests. Le rapport final indiquera la révision corrigée et les replays correspondants ; un fichier dirty n'est pas assimilé à un commit vérifié.

Aucun appel LLM, génération payante, exécution du produit sur Windows, modification de la campagne historique, arrêt global, suppression de ressource étrangère ou édition du tableau partagé. Les seuls nouveaux fichiers sont ce rapport et les contre-tests/proofs de superviseur dans mon propre worktree. Docker/suppression/provider sont remplacés dans les contre-tests ; le test d'annulation utilise un thread inerte et libère toujours sa barrière.

## Conclusion et périmètre

Trois P1 distincts de lifecycle ont été reproduits puis corrigés par leurs propriétaires, et les contre-tests passent sur la cible propre `88b79de1c84dd813042710df8468e7d618d5728c`. Une quatrième faiblesse de garde API est reproduite ci-dessous et devient un lot correctif distinct, explicitement attribué par le parent. Pas de nouveau défaut démontré dans la frontière Docker automatisée. **La clôture REM-24 n'est pas déduite de cette revue** : la garde API, la globale finale et la preuve stricte des trois interruptions effectives REM-03 restent à terminer.

Lecture critique principale : `owned_publication.py`, `owned_packages.py`, façades contractuelles de `docker_deploy.py`, appels `arecover_publication`, `areconcile_deploy`, `aundeploy`, `_adocker_qualified_delivery`, API de suppression/déploiement/reprise, lien GUI, `delivery_raccord.py`, intégrité des reports/cache et rapports natifs. Mes propres modules contracts/claims/browser/quality/security ne reçoivent pas ici une seconde « revue indépendante » de leur auteur ; leurs résultats sont seulement classés comme preuves de fabrique, et les raccords parent sont relus.

## Défauts reproduits avant correction

1. **P1 — DELETE d'un contrat utilise le nettoyage legacy ou ignore son journal.** `api/server.py`, ancien `adelete_project` : condition basée sur image/CID/status persistés, puis `undeploy(project_id)` sans racine externe. Après crash avant flush, l'API supprime le workspace sans consulter le journal ; avec état flushé, elle emprunte les noms legacy/latest. Preuve HTTP ASGI : huit cas web/CLI × état flushé/non flushé × pipeline présent/absent, tous FAIL en 3,76 s (`delete-before-v2.xml`). Tous les effets externes sont remplacés. Correction attendue : sélectionner une autorité journalée même sans CID, préserver l'état sur retrait non confirmé, jamais supprimer par SHA/latest. Inspecter les deux journaux pour ne pas perdre un artifact plus ancien est une politique valide : le contre-test actuel accepte deux opérations, chacune avec exactement une racine de registre.
2. **P1 — CancelledError abandonne le thread de publication qualifiée.** L'ancien `_adocker_qualified_delivery` attendait directement `asyncio.to_thread` sans `self._docker_worker`/shield. L'enveloppe `_adocker_delivery_phase` retournait déjà alors que le worker était encore à sa barrière : 1 FAIL en 0,68 s (`cancel-before.xml`). La libération du cycle pouvait donc précéder le reçu/cleanup et une suppression de workspace. Correction attendue : handle de task retenu, drainage protégé même contre annulations répétées, traitement du vrai reçu et retrait seulement d'une création de cet appel.
3. **P1 — Le retrait intentionnel n'est pas journalisé avant la mutation Docker.** `PublicationRegistry.stop` écrivait `stopped` après close/rm. Une panne du flush terminal laisse le journal `running` et le CID absent ; le startup `intended_active_only=True` recrée le service. Contre-test FakeDocker : 1 FAIL en 1,84 s (`stop-intent-before.xml`). Correction attendue : intention `stopping` durable avant toute mutation, refus d'auto-reprise, retry explicite idempotent et volume conservé.

Le premier lancement du contre-test DELETE (`delete-before.xml`) a huit erreurs d'exécution asyncio faute de marqueur explicite dans un fichier extérieur à la configuration backend. Ce lancement ne démontre aucun défaut de production ; le marqueur a été ajouté et le vrai replay est v2. Aucun xfail/skip ne remplace les assertions rouges.

## Points positifs vérifiés et limites exactes

- L'intention de création du service est atomique et externe avant demande de volume/conteneur. Le registre recapture CID immuable, heure de création, fingerprint complet, volume local avec UUID/labels/CreatedAt, image/source/CMD/entrée exacts. Une identité étrangère, configurée différemment ou ambiguë bloque accès/cleanup ; un port occupé ne donne aucun droit de tuer son occupant.
- La publication part de l'image **déjà admise**, avec CMD baked et sans override/overlay. UID 65532, readonly, capdrop ALL, no-new-privileges, NETNONE, aucun port Docker publié ni Docker socket ; seul le volume DB exact est inscriptible. Les migrations source-revues ont un UUID temporaire journalisé et s'exécutent avant le lancement. Migration pending/failed bloque la reprise ; aucun seed ou réparation implicite ne sauve une readiness.
- Un changement de spec/image/contrat est refusé devant un service existant : pas de remplacement clandestin sans politique migration/rollback. Le chemin de publication normal ne génère ni Dockerfile ni réparation LLM. Le statut HTTP 2xx est une readiness locale, **pas** un oracle SEC/FUN ni une nouvelle qualification.
- Un package possède seulement son alias UUID, préparé après preuve d'absence et avant tag. Fresh inspect contrôle l'ID/CMD/source ; detach retire cet alias, jamais l'image par SHA ni un tag partagé. Le reçu `created_package_alias` distingue création réelle et réutilisation après crash avant flush.
- `load_qualified_delivery_image` réadmet reports complets, preuves X/R/V intactes, snapshot/contrat et bindings revus, puis le reçu natif de build/CMD actuel. Le ready flag persistant seul n'autorise rien. Les reports mal formés, IDs manquants/doublons, preuves obsolètes ou hors racine et attentes divergentes sont refusés. Le cache de revue couvre request_hash/phase/protocole/moteurs ; R dédiée SEC-05 n'est pas l'approbation générique des bindings.
- Reprise d'ingress : même CID et volume si le daemon les conserve ; source du workspace non remontée et aucun LLM automatique. Un stop confirmé ne doit pas être repris automatiquement. Une reprise d'un ancien service décrit ce service, pas l'acceptation d'une source plus récente.
- Le GUI utilise `127.0.0.1`, donc l'Origin publié exact. Ce lien ne prouve ni la qualification ni le confinement d'un navigateur utilisateur ouvert volontairement. Le navigateur **de validation** a sa frontière Docker NETNONE possédée, sans Chromium hôte nominal ; restart exige une nouvelle liaison explicite, jamais l'adoption d'un ancien namespace. Cette frontière a été écrite par moi : preuves et contre-revues pairs restent requises, pas auto-approbation dans ce rapport.
- Limites supportées explicites : Python/Node, IPv4 loopback, chemin SQLite factory précis, migration par argv littéral ; pas publication Internet/TLS, upgrade cross-version ni garantie contre compromission Docker/kernel/CLI. Les environnements/capacités indisponibles restent refusés, pas fallback hôte.

## Preuves lues et replays de cette revue

- Mon replay complémentaire : **182 PASS, rc0, 50,51 s**, `factory-mechanics-review.xml`. Modules : generation_recovery_remediation, activity_remediation, repair_policy, storage, dependencies_atomic, rem_dependencies, qa_provenance_raccord, source_reviewer, external_review_handoff, review_plans, review_delivery, delivery_raccord, budget_tracker_reservations, budget_reservations. Vrais processus Windows de fabrique et atomics kernel dans fixtures possédées ; ports/verdicts opérationnels des métatests restent synthétiques. Pas de génération payante ni produit sur l'hôte.
- Native publication/packages rem_execution : JUnit et JSON de REM-01 lus ; image/CID/volume exacts, mutation SQLite conservée après handoff, mort de processus Windows, stop/restart, canaries egress refusés, alias partagé préservé, migration avant startup strict. Ce sont des **fixtures indépendantes**, non Relais Support généré.
- Replay parent plus récent : `C:/Dev/squad-ai/Brainstorming/Autospec/workspace/remediation-20261011/owned-publication-parent-v2.xml` : **37 PASS, 0 FAIL/ERROR/SKIP**, temps JUnit 184,212 s (temps commande parent 184,27 s). Il précède le dernier correctif d'intention de stop ; pas recyclé en preuve de ce nouveau code.
- Dernière globale conservée : `full-regression-third-snapshot.xml`, snapshot `8dffd0e8`, **2 583 PASS / 10 FAIL / 74 SKIP**, temps JUnit 3 296,233 s (temps commande 3 299,91 s). Le replay des quatre modules à deadline Windows donne 154 PASS, mais n'efface pas cette globale rouge. Un nouveau replay global sur commit final est annoncé, non supposé exécuté.
- Bootstrap/coverage mis à niveau : vrais React frontend/fullstack Linux + Chromium Docker, locks exacts et audit zéro ; Vitest 2 et 4 source-inventory complet et untouched zéro prouvés. La couverture scaffold 8/17 = 47,06% est une preuve de collecte, **pas** le seuil TST-03 satisfait.
- Source reviewer/cache/audits : réponses locales de deux identités GPT distinctes, liées au paquet exact et phases ; pas appel Claude de revue, pas X/V fabriqué par R. Audit unavailable ne passe pas ; acceptation de risque nécessite reçu humain dédié au sujet, pas une opinion du classificateur.

Les rapports intermédiaires rouges restent conservés. Les opt-ins natifs d'une suite locale ne sont pas des skips critiques du produit et ne deviennent pas PASS par addition de plusieurs rapports. Les sources v0.2 ont été re-hashées : brief `0a99950d…fb0f3`, référentiel `efdab8ea…cbf4`, faits approuvés `f2b3105f…44b9` : mêmes octets attendus. Les faits source ne sont pas des verdicts.

## DoD REM-01 à REM-23 : proposition de libération

« Libérable fabrique » ci-dessous signifie capacité/raccord et contre-exemples prêts à décision du coordinateur, **après** dependencies DONE et replay commun final ; jamais PASS du futur produit. Aucun statut du tableau n'est édité ici.

| ID | Avis à la portée fabrique | Preuve / réserve à ne pas confondre |
|---|---|---|
| REM-01 | Libérable sous frontière relue et globale finale | CLI tool-less/broker, canaries Docker, refus backend non qualifié et Chromium Docker. Trust CLI/kernel/daemon explicite ; pas inférence payante de qualification. |
| REM-02 | Attendre dernier lifecycle corrigé et replay | Jobs Windows réels, A/B/sentinelle, identités/cleanup ; trois P1 ci-dessus concernent les nouvelles sorties publication/API. |
| REM-03 | Complément strict de preuve demandé | Persist/restart/crash-before-flush/cost-incomplete prouvés. Les trois programmes natifs écrivent stage puis sleep : ils ne meurent pas au milieu d'un provider, merge et smoke effectifs. Une barrière sur vrai workflow superviseur (FakeRunner permis) serait la preuve exacte de la fiche. |
| REM-04 | Libérable fabrique | Demandes sérialisées, unions manifest/lock et clean Argon2 ; vrais locks npm11/Vitest4, pas paquet injecté hors lock. |
| REM-05 | Libérable aux capacités annoncées | Images/recipes/env hashes et installs propres, cache invalidé, absence host fallback ; ne promet pas toutes stacks. |
| REM-06 | Libérable fabrique | Baselines empoisonnées refusées à chaque admission, QA helpers externes avant write, collecte/skip/xfail contraints ; corpus natif distinct de 57 verdicts. |
| REM-07 | Libérable après prérequis | Classification/répétition/deadline/cap testés ; aucun contournement d'un defect par skip ou boucle payante illimitée. |
| REM-08 | Libérable fabrique | Décision structurée scellée, contradictions, React/prose « vue », stack unsupported honnête. |
| REM-09 | Libérable mécanisme ; auteur non indépendant ici | 57 IDs/56 obligatoires, oracle extérieur scellé, autre application et quatre faits v0.2 approuvés ; pas oracle issu du futur code. |
| REM-10 | Libérable mécanisme ; raccord parent revu | Invariant violé bloque malgré score, juge invalide failclosed, findings confirmés résolus, sept lots explicites distincts de 27 tâches. |
| REM-11 | Libérable après REM-04/10 | Racines Windows/POSIX/casse/stream, globs futurs et dépendances communes ; limite de sur-sérialisation des globs conservatrice. |
| REM-12 | Libérable après REM-11 | Arbiter pré-write, un writer, reprise/collision ; verrou asyncio par superviseur, pas prétention de lock distribué multi-hôte. |
| REM-13 | Libérable capacités Python/React/SQLite et refus | Probes propres API/DB et vraie réponse nonce du frontend ; replay idempotent. Go/Rust unsupported explicitement, pas substitution cachée. |
| REM-14 | Libérable jalon fabrique | Réel Argon2/login navigateur/création API/DB, image exacte et dépendants bloqués ; jalon étroit ≠ 57 acceptance. |
| REM-15 | Libérable pack après raccord commun ; pas ma contre-revue propre | Bon/mauvais HTTP/SQLite/Argon2, invariants X/R et preuve d'entropie réelle ; R fixture synthétique non réutilisable en campagne. |
| REM-16 | Libérable pack après raccord commun | Matrices métier, CAS/races DB distinctes, rollback/replay ; réponses UI ont contribution navigateur same-snapshot séparée. |
| REM-17 | Libérable pack après raccord commun | SQL contraintes/trace/types, DTO/routes et clocks natifs ; absence de port/custom driver reste NV, pas auto-PASS. |
| REM-18 | Libérable pack après frontière et replay commun ; auteur exclu de revue propre | Bon/mauvais callback401/UUID/search/conflit, desktop/mobile/clavier et V exécutés ; aucun texte/marker opérationnel ajouté à l'oracle. |
| REM-19 | Libérable collecteurs après dependencies/replay commun | Six parcours source-exacts exécutables seuls/ensemble, inventaires complets et mutation exigeant vrai kill X ; seuils sur futur snapshot encore à mesurer. |
| REM-20 | Attendre dernier lifecycle et replay commun | CMD baked/image exacte/volume/README/audit natifs ; trois P1 de retrait/annulation relevés. Aucune acceptation implicite d'audit high/critical. |
| REM-21 | Attendre lifecycle, REM-19/20 et replay final | Admission exhaustive hashes/attendus/X/R/V et séparation DONE/deployed/ready ; pas qualification par un flag ou score. |
| REM-22 | Libérable mécanique/télémétrie | Attentes budget/claims/outils/providers distinctes, clocks et coût incomplet ; diagnostics de durée ≠ garanties produit ni facture. |
| REM-23 | Libérable en décision OFF/différée explicite | Réservations/races/late receipt/crash, coût connu préservé ; production Claude non qualifiée pour hard billing, donc sérialisation conservée, gain production non mesuré. |

REM-24 reste en contre-revue tant que correctifs/tests communs/complément REM-03 ne sont pas arbitrés. REM-25 reste la seule évaluation d'une nouvelle sortie : même v0.2, 57 lignes complètes, 56 B/M PASS requis, OPS-06 séparé. Les centaines de PASS de fabrique de ce dossier ne deviennent **aucun** PASS produit.

## Annexe — confirmation sur cible stable et quatrième garde

Révision propre avant et après le replay : `88b79de1c84dd813042710df8468e7d618d5728c`. Le correctif lifecycle est dans `f43ba62c` / intégration `ffaa49af`, les raccords parent dans `b32d9f55`. Relecture du dernier code : `stopping` est durable avant mutation et non réadmissible ; les retries de stop restent explicites. `created_publication_container` est un reçu de création de cet appel, jamais une différence avec le state UI ; cleanup sous verrou compare le CID courant. Reuse re-hashe la source après inspection/readiness, tandis qu'une adoption annulée ne supprime pas le daemon/DB préexistant. La façade parent conserve `intended_active_only` et transmet l'annulation.

Mon replay : **118 PASS / 3 SKIP, rc0, 31,55 s**, `owned-delivery-corrected-88b79de1.xml`. Les trois skips sont les deux probes publication Docker et le probe package Docker, explicitement opt-in ; ils ont été exécutés séparément dans le replay pair **58 PASS / 194,06 s** (`REM-01/20261012-owned-lifecycle-native-v3.xml`). Les dix variantes de mes trois contre-tests initialement rouges sont toutes exécutées et PASS. Les modules rejoués sont owned_publication, owned_packages, publication_raccord_recovery, owned_delivery_lifecycle_guards, budget_cache_resume_guards et delivery_raccord. Le parent conserve aussi son replay combiné **146 PASS / 18,70 s**, `owned-budget-cache-root-v3.xml`. Les tests sont de mécanique de fabrique, pas des verdicts du produit.

Hashes des sources au replay stable :

| Fichier | SHA256 |
|---|---|
| owned_publication.py | a1207843c6b16ef3ef4cde49063d661d296241d9716e8891e8764a9bc3ad3436 |
| owned_packages.py | 468ccefcfb014edcbf57651ad7391ae6fbfc8c43c19ee425f7d398c79abb3dff |
| docker_deploy.py | 4b07c07318ee0e0910e18d3181d9c532c7d6082e21c187c87bc69692f5ef775a |
| pipeline.py | cfb29e6e3a52782ef9f74bc1f00fa8c1b30d3bbc926c480f5e74bb48c610092a |
| api/server.py | ccd615be27930e0a15167f7167dc715cdd524fa7c32d598dd296705a2078da69 |
| final_gate.py | 4dd17b1685d63e4cab2c93190dd184c12d9c133b643ac03474ab6e01029c553e |
| delivery_raccord.py | 34313afa1d3d46ab0cc151a69eb835d7d61e08e7b6728c7ab35cc84e3ecfde97 |

**P1 — API de contrôle accessible en mutation simple depuis une origine étrangère.** CORS seul empêche la lecture, pas l'exécution d'un POST simple. Après ouverture volontaire du produit dans le navigateur utilisateur, hors harness Docker, une page peut demander `/api/projects/<id>/undeploy`. Le contre-test ASGI n'exécute aucun JS ni Docker : callback inerte atteint depuis une origine produit loopback, un tiers HTTPS et `null`, **3 FAIL / 0,75 s** (`foreign-origin-before.xml`, `test_foreign_origin_counterproof.py`). Les IDs sont connus dans cette fixture ; ce test ne prétend pas prouver la découverte automatique d'autres projets ni une compromission du navigateur.

Le parent confirme que cette protection fait partie du périmètre avant campagne et m'attribue sa correction à partir de `88b79de1`. Origin absent reste permis aux clients locaux ; Origin présent doit être usine explicitement approuvé/configuré ou origine serveur loopback exacte. Host non-loopback/DNS-rebinding, y compris GET sans Origin, doit être refusé sans configuration explicite. Pas d'exception `test/testserver`, de bypass ASGI, d'authentification magique ni de CORS wildcard. La migration de clients de tests usine vers `127.0.0.1` ne modifie pas les fixtures produit. REM-01/21/24 restent donc conditionnés à ce nouveau lot et au replay final. Cette attribution n'est pas une quatrième correction déjà terminée.

L'attribut Git local `*.xml -text` conserve désormais les octets CRLF bruts des traces pytest. Le premier commit avait normalisé ces quatre XML ; ce second checkpoint restaure les octets actuels originaux sans changer les verdicts ni les sources. Les preuves précédentes restent dans l'historique ; aucun rouge n'est effacé.
