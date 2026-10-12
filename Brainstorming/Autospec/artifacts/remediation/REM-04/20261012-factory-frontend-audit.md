# Audit natif des dépendances frontend de la fabrique

12 octobre 2026. Contexte distinct de la nouvelle génération Relais Support : ce relevé ne constitue ni un verdict produit ni une acceptation de risque humaine.

`npm audit --json`, exécuté sur le lock existant du snapshot de régression `8dffd0e8cfb47324637ea3c3007e5561ac3bb587`, retourne **1** : 12 paquets signalés, 4 moderate, 6 high, 2 critical. Le JSON brut est conservé dans [20261012-factory-frontend-audit.json](20261012-factory-frontend-audit.json). Aucun `npm audit fix`, aucun `--force`, aucune modification automatique du lock n'a été exécuté.

Le serveur de production de la fabrique sert le frontend compilé avec FastAPI ; les commandes utilisées dans ce replay sont `tsc && vite build` et `vitest run`, pas Vitest UI/Browser Mode. Ce fait réduit certaines surfaces, mais ne prouve pas l'absence de toute exploitation.

- [GHSA-5xrq-8626-4rwp](https://github.com/advisories/GHSA-5xrq-8626-4rwp) concerne notamment Vitest UI exposé ou UI/Browser Mode Windows. Ces modes ne sont pas employés dans ce replay. Les versions installées restent néanmoins affectées selon l'audit.
- [GHSA-5gmw-xhrv-c9v3](https://github.com/advisories/GHSA-5gmw-xhrv-c9v3) décrit un gadget de pollution de prototype dans Tinypool : une primitive préalable de pollution est nécessaire. Son absence dans les chemins actuellement testés n'est pas une preuve exhaustive.
- [GHSA-fx2h-pf6j-xcff](https://github.com/advisories/GHSA-fx2h-pf6j-xcff) concerne le serveur de développement Vite Windows. La production statique et le build ne doivent pas être confondus avec ce serveur.

Les autres avis et leurs plages exactes restent dans le JSON ; aucune classification d'exploitabilité production n'est inventée. Les versions de templates générés sont un sujet séparé : leurs audits seront effectués sur leurs propres locks exacts. Les tests de source générée, build et navigateur passent par Docker NETNONE, pas par les outils hôte.

Action restante : qualifier une mise à niveau minimale cohérente des dépendances et des templates, avec installation verrouillée, tests unitaires, build et E2E ; aucune acceptation de risque implicite. Ce relevé ne suffit pas à clore REM-04/REM-24.
