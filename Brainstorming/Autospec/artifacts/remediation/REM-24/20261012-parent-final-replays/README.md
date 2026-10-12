# Replays du coordinateur — 12 octobre 2026

Ces résultats testent la fabrique et ses frontières. Ils ne constituent pas une
acceptation du futur produit Relais Support, ni une suite globale finale verte.
Les échecs historiques et leurs JUnit sont conservés dans REM-21.

| Rejeu terminé | Résultat | Portée |
|---|---|---|
| Modules contenant les 14 échecs de la deuxième globale | 146 PASS, 182,25 s | Régression locale Git, rollback, manifests, canaris et workflow |
| Frontend Autospec | 308 PASS, 24,15 s | 30 fichiers de tests unitaires ; compilation tsc/Vite réussie séparément |
| UI Autospec exhaustive + activité/extension | 2 PASS, environ 1,5 min | Backend réel sur 8123, agents simulés, workspace de test dédié |
| UI multi-stream | 1 PASS, environ 1,3 min | Backend réel sur 8124, agents simulés, workspace de test distinct |
| Image CMD native + navigateur Docker + RuntimeSession | 27 PASS, 74,09 s | Python main:app sans __main__, Node ESM, lancement image sans overlay, réseau NETNONE, refus localhost hôte/UDP externe, lifecycle |
| Raccord preuve/CMD/horloges/revue/cache typé | 72 PASS, 7 SKIP, 1,69 s | Les 7 skips sont des opt-ins natifs distincts ; doubles explicites des ports de métatests, pas une qualification produit |

Le navigateur du test Docker est non-root/read-only dans l'espace réseau du
conteneur NETNONE possédé. Sa preuve et capture sont retenues ici. Les IDs
Docker aléatoires ne sont plus actifs après cleanup ; ce résultat ne promet
pas une protection contre une faille du kernel ou du moteur Docker.

Les paramètres Playwright autorisent maintenant AUTOSPEC_TEST_PYTHON pour
réutiliser l'environnement verrouillé de la fabrique, sans fabriquer une venv
historique dans le worktree. Aucun appel Claude, export de code vers Claude,
activation de crédits ou modification du produit de la campagne initiale.
La démo 18004 et la campagne initiale 8126 n'ont pas été utilisées par ces tests.

Une commande de replay a d'abord cité un nom de module inexistant
test_native_clocks.py : pytest n'a collecté aucun test. Le replay v2 utilise le
module réel test_delivery_timing.py ; aucun vert n'est déduit du premier appel.

Restent avant lancement REM-25 : contre-revue du bootstrap navigateur intégré,
disposition explicite des arbitrages d'audit, publication de l'image exacte et
nouvelle suite commune. Le rapport de campagne devra ensuite couvrir les 57 IDs.
