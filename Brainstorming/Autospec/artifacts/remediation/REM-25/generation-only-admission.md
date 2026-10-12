# Admission de campagne : génération Claude, revue GPT

État : implémentation et tests superviseur locaux ; aucune génération lancée par cette preuve.

Le benchmark active `GENERATION_ONLY_AGENTS=true`. `make_runner` refuse alors tout provider autre que `claude code` (harness abonnement). Les labels `claude` et `anthropic` désignent une API directe et sont explicitement refusés. Le mode générique, désactivé par défaut, conserve ses fonctionnalités.

Le wrapper admet uniquement les personas de préparation et de génération énumérées dans `GENERATION_ROLES`, impose Sonnet et refuse les rôles inconnus ou de revue, notamment critic, judge, security-reviewer, evaluator et independence-judge. L'admission précède le journal d'activité, les réservations et le checkpoint dans `_UsageTracker`; elle contrôle aussi le routage par rôle, l'escalade et les overrides. Le wrapper recontrôle le modèle effectif avant son runner interne. Les refus attestés avant appel ne deviennent pas un usage historique inconnu.

Le rôle `qa` reste autorisé pour la génération des tests et le retour technique au développeur, sans constituer la revue indépendante ni une preuve d'acceptation. Les revues R et le jugement final restent externes, effectués par les sous-agents GPT explicitement demandés. Les options REFINE, SECURITY_REVIEW, EVALUATOR, INDEPENDENCE et LANGFUSE doivent rester désactivées dans le launcher de cette campagne. Aucune assertion de conformité ne provient du nom d'un rôle.

## Preuves locales

- `generation-only-policy-root-v4.xml` : 71 PASS, 1,44 s. Personas permises/interdites, modèle imposé, trois voies de changement de modèle, six providers interdits, compatibilité du mode générique, inventaire de capacités sans création de runner, tests provider/API et contre-tests budget/cache.
- `generation-only-policy-root-v3.xml` : 67 PASS, 1,43 s, avant les quatre assertions supplémentaires de routage et d'inventaire.
- `generation-only-policy-root-v2.xml` : conservé, 21 FAIL / 46 PASS pendant le développement. Deux défauts de raccord étaient présents : la garde avait été insérée dans l'inventaire de capacités plutôt que dans `make_runner`, et les fixtures de rôles admis ne fournissaient pas de réponse FakeRunner. Ces erreurs ont été corrigées ; elles ne sont pas des échecs du produit généré.

Commande : Python de l'environnement superviseur, `-m pytest backend/tests/test_generation_only_policy.py backend/tests/test_providers.py backend/tests/test_api_provider.py backend/tests/test_anthropic_provider.py backend/tests/test_rem24_budget_and_cache_counterreview.py --junitxml=<preuve> -q`.

Limites : runners fictifs et tests d'admission, aucun appel Claude/OpenAI, aucune authentification vérifiée ici, aucun coût engagé, aucune exécution de code généré sur l'hôte. Le login Team, les flags de campagne, le budget estimé de 40 USD et l'isolation doivent faire l'objet d'un préflight frais avant lancement. Cette garde n'est ni une frontière d'isolation ni un contrôle de facturation.
