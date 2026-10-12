# Préfixes de coûts connus sur erreur/cancellation — 2026-10-12

Défaut confirmé par lecture : après un premier tour payé/rapporté, un deuxième _turn levant AgentError sans usage effaçait le préfixe connu pour le tracker. La réserve restait entière et bloquait l'admission (pas de faux hard-bound), mais le coût déjà connu disparaissait de la comptabilité. Une erreur du coordinateur/filetool pouvait perdre aussi ce préfixe.

ClaudeCliRunner accumule maintenant le reçu avant cleanup observer, puis attache une copie du cumul à chaque erreur. Dernier tour entré sans reçu final : usage_reported=False, coût préfixe conservé, réserve restante requise. Erreur ou cancellation durant médiation/outils après reçu complet : cumul connu conservé, aucune inference supplémentaire inventée. asyncio.CancelledError porte aussi usage, pour que le tracker puisse comptabiliser le partiel connu et conserver la réserve si complete=False. Le parent doit lire exc.usage dans ses deux branches cancellation (_arun accounting + arun reconcile), pas le remplacer par None.

Tests : timeout/failure après premier tour avec ou sans reçu partiel, reçu final connu, refus callback AgentError/OSError, cancellation au milieu du deuxième tour, cancellation pendant attente outil, erreur observer après réponse payée. Aucun coût fictif zéro/substitut d'estimation. Providers exclusivement scriptés offline; aucune API modèle/commande produit hôte.

`pytest tests/test_mediated_usage_prefix.py tests/test_restricted_execution.py tests/test_budget_reservations.py tests/test_owned_execution.py -q` : **73 PASS, 3 SKIP / 3.60s**. Les skips sont les probes explicitement opt-in/native indisponibles du corpus existant; les nouveaux tests sont tous exécutés. Les deux FakeCLI réels de réservations sont toujours offline et gardent la preuve de concurrence/plafond fake.

Raccord parent encore nécessaire avant clôture : consommation du coût attaché à cancellation. Une réserve conservée n'autorise pas à effacer le coût connu; une erreur outil sans nouveau tour ne prouve pas un coût provider supplémentaire.
