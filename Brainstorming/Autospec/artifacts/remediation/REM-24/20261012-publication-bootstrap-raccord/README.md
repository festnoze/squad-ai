# Raccord publication, audit et fondation — revue parent

12 octobre 2026. Base d'intégration `9759576f` plus modifications de raccord identifiées dans le commit contenant ce dossier. **Tests de fabrique et fixtures dédiées ; aucune nouvelle génération Relais Support et aucun PASS parmi ses 57 critères n'est déduit de ces résultats.** Les ports natifs mockés le sont uniquement dans les tests de mécanique d'admission.

Interpréteur : environnement verrouillé `workspace/remediation-20261011/factory-env`, Python 3.14.5. Les ressources des tests restent dans les répertoires temporaires, comptes fictifs et conteneurs NETNONE possédés ; aucun appel LLM facturé.

| Preuve | Résultat réel | Portée et limites |
|---|---|---|
| audit-disposition-root.xml | rc0, 108 PASS, 8 opt-ins SKIP, 11,19 s | Audit typé, provenance, refus/rejet et absence d'approbation humaine ; aucun waiver réel accordé |
| qualified-publication-raccord.xml | rc0, 60 PASS, 6,32 s | Qualification avant publication, réadmission des reports/image/CMD, refus de drift ; mécanique et mocks de ports natifs, pas publication fonctionnelle |
| api-isolated-countercheck.xml | rc0, 59 PASS, 230,07 s | Module API complet isolément ; ne remplace pas le replay global sur snapshot figé |
| final-typed-publication-bootstrap-unit.xml | rc0, 186 PASS, 23 opt-ins SKIP, 26,39 s | Sept modules de raccord, cycle navigateur et réponses nonce ; avertissement de dépréciation Starlette conservé |
| bootstrap-parent-api-real.xml | rc1, 2 FAIL, 47 PASS, 15 SKIP, 163,69 s | Premier contrôle trop tardif : navigation initiale implicite puis attente d'une seconde réponse ; échec conservé |
| bootstrap-api-positive-debug.xml | rc1, 1 FAIL, 4 deselected, 16,51 s | Diagnostic initial de lecture de réponse ; aucune réussite déclarée |
| bootstrap-parent-api-real-v2.xml | rc1, 1 FAIL, 4 PASS, 142,40 s | Navigation initiale désactivée avant expect_response : frontend seul et fullstack réels passent, faux texte et mauvaise nonce refusés ; fixture positive HTML sans enfant root incorrecte |
| bootstrap-api-counterexamples-v3.xml | rc0, 3 PASS, 2 deselected, 59,52 s | Fixture positive corrigée `<p>` ; réponse frontend réellement observée, faux texte/mauvaise nonce refusés, aucun affaiblissement du contrôle |
| claims-root-counterreview.xml | rc1, 2 FAIL, 43 PASS, 112,82 s | Deux tests scheduler dépassent leur délai 40 s sur Windows ; pas de succès global déclaré |
| scheduler-standalone-countercheck.xml | rc1, 1 FAIL, 53,01 s | Échec reproduit isolément ; journal observé : deux tâches bien mergées et story DONE après environ 45 s. Le coût Git/processus réel doit être mesuré avant toute adaptation du délai de test |

La publication contractuelle ne reconstruit plus l'image, ne régénère pas de Dockerfile et ne lance pas de réparation payante après qualification. Le chemin minimal conserve actuellement une image qualifiée mais refuse de déclarer une application web déployée tant que la publication durable NETNONE n'est pas disponible. Une infrastructure manquante ne vaut ni réussite ni défaut métier prouvé.

Le socle React + FastAPI + SQLite a été exécuté dans des conteneurs réels et le navigateur Chromium se trouve dans le namespace NETNONE exact de son parent. Le contrôle exige maintenant un GET réel `/api/health` initié pendant la navigation du frontend, HTTP 200 et JSON exact avec nonce superviseur, puis l'affichage. Du texte statique `OK` ne peut plus remplacer l'appel API.
