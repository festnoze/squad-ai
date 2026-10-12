# Revue AFTER — deux P1 budget/cache corrigés

Cible clean : `88b79de1c84dd813042710df8468e7d618d5728c`, incluant le correctif
root`b32d9f55`, le correctif d'auteur mode`1b3f974a` et le contre-test réel
`05074b5c`. Source de cette cible en lecture seule pendant les tests : aucun
diff source après le run. Seuls ces nouveaux artefacts sont écrits.

Conclusion bornée : **les deux P1 de REVIEW.md sont corrigés sur cette cible**.
Les contre-tests n'ont pas été modifiés ni assouplis pour l'AFTER. Aucun nouveau
P0/P1 confirmé dans ce replay, aucune requalification globale ou produit induite.

## BEFORE → AFTER, mêmes invariants

- BEFOREc1e21400 : `counterexamples-v3.xml`,6FAIL/1PASS/1.69s.
- AFTER88b79de1 : `counterexamples-after-v1.xml`, **7PASS/0.69s**, rc0.
- SHA256 du fichier de contre-tests inchangé :
  `cb66c862da7854a256eda8dd3656871830459ece153f625c4cc8f4615198efd3`.
- Deux budgets historiques (USD et tokens), reprise explicite et nouveau
  feedback ne dispatchent plus le runner scripté tant que l'usage perdu reste
  non réconcilié. Le contrôle nominal avec historique connu passe toujours.
- Le port mock de contexte refusé est effectivement appelé avant le cache.
- Le vrai protocole local `ensure_reviewed_configuration` refuse un contexte
  engine altéré avec `ReviewPending`; la gate finale reste maintenant non-ready.
  Les proposer/reviewer/R/X de ce métatest sont synthétiques et explicitement
  étiquetés ; aucune conformité du produit copié n'est attestée, aucun code de
  ce produit n'est importé ou exécuté sur l'hôte.

Lecture du correctif root : `_UsageTracker.arun` refuse`COST_UNREPORTED` AVANT
activité/réservation/checkpoint/provider ; `_enforce_budget` conserve ce stop,
y compris cap modifié/désactivé. Aucun compteur n'est remis à zéro et aucun
coût inconnu n'est estimé comme final. La revalidation source-review est
systématique AVANT consultation du cache final. `verification_cache_context`
lie rapports à SHA du code de la fabrique et aux scellés exacts, plus code/
contrat ; le SHA des reports est relu et le contexte est revérifié après
nouvelle collecte. Un report superseded est conservé comme historique.

## Replay strict du corpus de départ

`supervisor-after-v1.xml` / `.log` : **277PASS/4SKIP/57.72s**, rc0,
Python factory verrouillé3.14.6. Même liste explicite des16 modules que BEFORE,
mêmes281identités `classname::name` (comparaison XML : zéro différence),
mêmes4skips ET motifs (zéro différence). Pas de nouvelle globale lancée.

Quatre opt-ins NON requalifiés :

- `tests.test_restricted_execution::test_native_cli_init_only_skips_product_hooks_and_mcp`.
- `tests.test_owned_execution::test_real_docker_nominal_and_adversarial_operations_preserve_host`.
- `tests.test_owned_execution::test_real_docker_timeout_cleans_only_its_owned_container`.
- `tests.test_native_quality_raccord::test_real_linux_collection_exports_exact_command_coverage_and_intact_x`.

Les fixtures Windows Jobs/FakeCLI/sentinelles du corpus sont réelles et
superviseur-revues ; les provider/Docker opt-ins ci-dessus sont explicitement
désactivés dans les deux commandes. Aucune génération, commande produit hôte,
inférence payante, revueClaude, historique/DB utilisateur ou tableau partagé.

Empreintes SHA256 des sources réellement lues/exécutées sous Windows :

- runner : `1b93b1ce9e09135391586ff33fe76a9eb78da55c526bf1132c1eea3ed819d3f3`.
- file_broker : `4013deaec7149a8ca89c4706c0c5039ee3b13ca9ca9cf14ba86a9f9dccdc910c`.
- pipeline : `cfb29e6e3a52782ef9f74bc1f00fa8c1b30d3bbc926c480f5e74bb48c610092a`.
- final_gate : `4dd17b1685d63e4cab2c93190dd184c12d9c133b643ac03474ab6e01029c553e`.
- source_reviewer : `31b086df1bd4af8754a32febb576db3ebfa5cfd13bb92050079bbf9fe124187e`.
- native_quality_raccord : `ba954f2114f597771db29083dea7617194845f862336269d9d3f69b355d248ae`.
- coordinator : `fc42555a308a945b69d746c82687b270c5532bc23890d57e986c77adcdd28c2e`.

SHA256 des nouveaux XML, conservés en octets exacts :

- counterexamples-after-v1 : `fb973e2df71046231498f23d0986fb8aef9f5e19462ef8e4dc94ae7896e8cd84`.
- supervisor-after-v1 : `d8565f2595a12a79121a205ef333eb727d65ac0bfd94fd34409e7675e1064c60`.

## Libération et limites restantes

Les findingsP1budget/cache de cette contre-revue peuvent être marqués résolus
par le coordinateur pour88b79de1. Cela ne supprime pas les limites du rapport
initial : dépendances/profils et helper mode dont je suis auteur ne constituent
pas ma revue indépendante ; quatre bancs natifs sont toujoursSKIP ici ; les
autres reviews/lifecycle/Docker conservent leurs propres preuves séparées.
Le root a également fourni son replay146PASS/18.70s dans
`REM-24/20261012-final-integration/owned-budget-cache-root-v3.xml` ; ce reçu
parent n'est pas compté une seconde fois dans les277.

Le prochain préflight du launcher reste **lecture seule, aucun démarrage**.
La politique generation-only de la campagne support doit être une admission
de rôle avant CLI, pas seulement REFINE/SECURITY_REVIEW/EVALUATOR/LANGFUSEOFF.
Ce wrapper n'est pas présent dans la cible88b79de1 : pas d'approbation de
lancement de ce seul AFTER. Voir le plan de lecture REM-25 séparé.
