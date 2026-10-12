# Contre-revue indépendante — exécution, interruption et admission

Cible : `c1e214000893bbbe889000e0699855b949bf18e1` (inclut `37fc3ec6`).
Révision lue dans les blobs commités ; le pipeline et les tests lifecycle encore
dirty du coordinateur ne font pas partie du verdict ci-dessous. Revue le12
octobre2026, sans changement de modèle, génération, provider réel, appel LLM
payant, code produit exécuté sur l'hôte ou modification du tableau partagé.

Verdict de cette cible : **deux P1 confirmés, qualification non libérée**. Aucun
P0 supplémentaire confirmé dans les frontières examinées. Une absence de
finding n'est pas une certification générale ni un PASS produit57/57.

## P1 — coût historique incomplet non bloquant après reprise

Chemins/points de raccord, relatifs à la cible :

- `backend/autospec/orchestrator/pipeline.py:712`, `_UsageTracker.arun` :
  admission du nouvel appel sans contrôle de `usage.unreported_calls` dans la
  lane sérialisée, qui est celle de Claude/REM-23 OFF.
- `pipeline.py:1934`, `_enforce_budget` : ne compare que USD/tokens connus.
- `pipeline.py:9132`, `aresume_build`, et branche feedback dormant de
  `asend_user_message` : remettent `_stop_requested=False` sans réconciliation.
- `backend/autospec/api/server.py:153` : le restart conserve correctement
  l'incertitude, puis la future admission ne la traite pas comme verrou.

Reproduction : nouvelle `OfflineReceiptRunner` entièrement scriptée,
`usage.cost_usd=0.1`, `unreported_calls=1`, phaseSTOPPED et checkpoint interrupted.
Le capUSD1 laisse dispatcher avec allowance0.9, bien que le coût du tour perdu
reste inconnu. Même résultat sous cap tokens100, reprise explicite et nouveau
feedback. Les quatre invariants sont rouges dans `counterexamples-v1.xml` ;
le contrôle nominal `unreported_calls=0` reste vert. Aucun vrai coût n'est
engagé par les contre-tests.

Impact : un retry ou redémarrage peut réutiliser un solde déjà potentiellement
consommé ; afficher l'incomplétude ne suffit pas à empêcher la dépense. Le
journal concurrent, lui, refuse les réservations non réconciliées : le défaut
concerne son absence, pas une preuve de cap fournisseur dur.

Proposition centrale, remise au coordinateur sans écrire son pipeline :

1. Avant journal, activité, checkpoint ou dispatch, `_UsageTracker.arun`
   refuse `COST_UNREPORTED` si un historique non réconcilié existe.
2. `_enforce_budget` maintient également le stop afin que start/resume/watchdog
   ou chat ne rouvrent pas cette admission. Désactiver/changer le cap ne doit
   pas effacer une incertitude historique ni servir de réconciliation implicite.
3. Seul un reçu définitif réellement attesté, associé à l'appel concerné et
   enregistré durablement, permet une réconciliation explicite. Ne pas remettre
   le compteur à zéro, deviner un coût ou doubler un préfixe payé connu.

## P1 — rapport final en cache court-circuite la revue courante

`backend/autospec/orchestrator/pipeline.py:4476..4503` : `admit_reports` peut
déclarer le cache ready avant `_await_reviewed_configuration`. Dans ce cas,
la branche qui vérifie le protocole, les moteurs de revue, les bindings,
fixtures, plans qualité/livraison et revue entropy est entièrement évitée.
`source_reviewer.py:157..212` invalide correctement ces contextes lorsqu'il
est appelé ; la présence de cette défense ne prouve pas son raccord.

Reproduction offline : un reportX/R synthétique de mécanique est intact et
lié au même code/contrat. Le port de revue courant est remplacé par un refus
`AdapterUnavailable('cached source review engine/protocol changed')`. La gate
retourne néanmoinsTrue, `delivery_ready=True`, sans appeler ce port. Le test
d'invariant attendu échoue dans `counterexamples-v1.xml`. Les reçus de ce test
sont explicitement synthétiques et ne prouvent aucun livre ni produit réel.

Impact : une correction des prédicats de sécurité/admission ou du protocole
de review ne rend pas périmé le vieux PASS si le code produit reste identique.
Les SHA des fichiers de preuves restent intacts mais ne disent pas quel
vérificateur/policy avait validé leur sémantique.

Proposition : appeler la revalidation de configuration/revue finale pour TOUTE
admission, avant le cache. Lier aussi le cache à une empreinte déterministe des
moteurs/prédicats/protocoles et des scellés exacts bindings/fixtures/qualité/
livraison/audit ; un contexte inconnu ou changé exige de nouvelles observations
et un jugement courant, pas seulement un nouveau booléen. Conserver les anciens
rapports comme histoire, sans les écraser en une prétendue preuve fraîche.

## Frontières examinées et éléments favorables

- `agents/runner.py`, `file_broker.py` : CLI dans un répertoire vide ; outils,
  hooks/customisations/MCP natifs désactivés ; Codex host-shell refusé ; shells,
  imports, suppressions et commandes ne sont pas des outils broker. L'environnement
  de génération est une allowlist qui ne transmet pas les API keys, NODE_OPTIONS
  ou sélecteurs de provider. OAuth reste au profil trusté, pas dans l'image/produit.
- Broker : validation du batch avant mutation, claims actifs via pipeline,
  manifests/checkers readonly, refus traversal/ADS/devices/8.3/links/reparse/
  hardlinks et racines oracles/configuration. Le producteur ne crée pas de
  writer parallèle hôte ; un acteur privilégié extérieur reste hors frontière.
- Windows Jobs : assignation suspendue avant reprise, kill-on-close,
  descendants détenus même après sortie parent ; pas d'arrêt par nom/PID nu.
  Nettoyage handles/jobs et I/O borné dans les bancs exécutés. Un Job n'est
  PAS le sandbox du code généré : ce dernier doit rester LinuxNETNONE.
- `test_integrity` / `pipeline_validation` : zéro collecte, IDs disparus,
  report incomplet, skip/xfail non revu, hash checker altéré et baseline
  refusée réutilisée ne deviennent pas GREEN. Les helpers QA hors conventions
  sont liés à un journal superviseur, pas à une déclaration du producteur.
- `native_quality_raccord` / `quality_contracts` : mesures obtenuesX ne sont
  pas verdictPASS ; échecs/couverture rouge restent dans les valeurs ; six
  parcours×deux modes ; mutation sur copie distincte exacte, original intact,
  vrais checksX nécessaires pour nominal/mutant. RevueR n'émet jamaisX/V.
- Source-review est exclusivement un paquet local pour deux agentsGPT distincts,
  lié request_hash/stage/phase/propositions/audit. Aucun `_tracked.arun` Claude
  de review n'a été trouvé. Même snapshot ne suffit pas à changer son sujet.
- `final_gate` contrôle IDs exacts/duplicates, attendu/gate du contrat, SHA,
  snapshot/contrat, scopes de checks, racine superviseur et typesX/R/V requis ;
  mandatoryFAIL demeureFAIL, NOT_VERIFIED ne se transforme pas enPASS.
- Réparations : classification, deadline réelle et répétition/attempts bornées ;
  canari natif absent reste non vert ; wrappers legacy de tests passent par Linux.
  Aucune preuve nouvelle d'un fallback host généré dans les appels examinés.

## Exécutions et identité des sources

`supervisor-v1.xml` / `.log` : **277 PASS /4 opt-in SKIP /92.40s**. Sélection
de16 modules explicitement listés dans le JUnit : restricted execution, owned
execution, runner processes, budget/cleanup/prefixes, recovery, repair policy,
baselines, qualité/plan/reviewer/finale et activité. Les handles/sentinelles
et FakeCLI Windows réels sont exécutés ; le code de leurs programmes est
superviseur-revu, pas celui d'un produit généré. Les tests de crash sauvegardent
et relisent un vrai état de worker détenu, avec labels provider/merge/smoke ;
ce ne sont pas des appels payants ni une campagne applicative complète.

Quatre SKIP conservés, **non requalifiés** :

- `test_native_cli_init_only_skips_product_hooks_and_mcp` (opt-in CLI offline).
- `test_real_docker_nominal_and_adversarial_operations_preserve_host`.
- `test_real_docker_timeout_cleans_only_its_owned_container`.
- `test_real_linux_collection_exports_exact_command_coverage_and_intact_x`.

`counterexamples-v1.xml` / `.log` : **5 FAIL /1 PASS /0.96s**, preuve BEFORE
des deux P1. `counterexamples-v2.xml` : **6 FAIL /1 PASS /1.03s**, ajoute
le self-check mode ci-dessous ; ces résultats rouges ne sont jamais présentés
comme un test de qualification vert. Le replay AFTER attend le SHA du root.

SHA256 des fichiers effectivement lus/exécutés sous Windows :

- runner : `1b93b1ce9e09135391586ff33fe76a9eb78da55c526bf1132c1eea3ed819d3f3`.
- broker : `4013deaec7149a8ca89c4706c0c5039ee3b13ca9ca9cf14ba86a9f9dccdc910c`.
- pipeline : `028466e9373312b3aaeb7e446673f5cee7a93810c2157330e1ceee3370f164de`.
- final_gate : `e322a3b895f9d54469f64dbb9cebd6cb358eb26aac66abac021ffe3f41cac1f2`.
- native_quality_raccord : `ba954f2114f597771db29083dea7617194845f862336269d9d3f69b355d248ae`.

## Limites et tâches libérables

DoD relues : REM-01/02/03/06/07/19/21/22/23 et interfaceREM-00, avec preuves
REM-01 execution/baseline/native-quality, REM-21 Linux/external-GPT/review-boundaries/
final-code, REM-23 reservations/prefixes/cleanup et derniers checkpointsREM-24.
Les vieux FAIL globaux sont conservés. Cette revue ne remplace pas la suite
globale finale, les probes lifecycle du root arrivant après cette cible, niREM-25.

- REM-01 : frontières broker/provider favorables à REVIEW après validation de
  la révision finale commune ; authTeam/Sonnet effective doit être recontrôlée
  avant campagne (aucun auth/model probe actuel exécuté ici). Les autres providers
  restent une capacité générique configurée, pas une autorisation de les utiliser.
- REM-02/03/07/22 : la partie handles/état/classification/attentes a ses preuves,
  mais pas de DONE commun avant correctionP1budget + lifecycle final revu/rejoué.
- REM-06 : défense baselines/QA de la cible non régressée dans le corpus ; les
  modules initiaux que j'ai écrits ne sont PAS ma contre-revue indépendante.
- REM-19/21 : non libérables tant que le cache court-circuite le contexte ; ne
  pas appeler des fixtures57PASS une nouvelle acceptance du produit.
- REM-23 : peut rester explicitement différé/OFF. Aucun hard cap financier de
  Claude qualifié ; aucun gain de parallélisme de production mesuré ici.
- REM-24/25 : non libérables de ce seul rapport. Le root reste propriétaire des
  statuts et de la décision de lancement ; pas de requalification automatique.

Autres limites : OS/CLI/daemon et store superviseur trustés ; pas de garantie
face à un écrivain hôte privilégié concurrent. Les receiptsX/R/V sont séparés
du code produit mais leur provenance humaine/agent est celle du superviseur,
pas une signature cryptographique d'identité de reviewer. Le tracingLangfuse,
si activé par la configuration trustée, transmet prompt/réponse complets :
il doit rester désactivé pour cette campagne sans autorisation distincte ; les
événements activité/cost examinés sont métadonnées, pas ce tracing opt-in.

## Correctif d'auteur séparé — pas une revue indépendante

Le helper `_quality_seal` du coordinator, que j'ai écrit, recalculait le hash
d'un plan `supervisor_browser` avec le mode par défaut`native`. La collecte
peer→publication échouait après12E2E ; pas fail-open, mais cache valide inutilisable.
Le coordinateur m'a rendu ce verrou après constat : code `1b3f974a` exige
mode explicite, le transmet au hash, et exige le tagR de mode superviseur.
Le nouveau `test_quality_seal_mode.py` est physiquement séparé des contre-tests
indépendants budget/cache. Six métatests positifs/négatifs mode PASS ; replay
coordinator/native-raccord/plan/mode : **54 PASS /3 opt-in SKIP /1.89s**,
`mode-regression-v3.xml`. Aucun passage de ce correctif ne vaut revue externe
de mes modules ou preuve de douze browser runs réellement répétés.
