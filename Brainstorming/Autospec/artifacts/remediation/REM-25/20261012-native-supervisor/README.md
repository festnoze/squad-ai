# REM-25 — préflight et superviseur natifs, sans génération

Révision source exacte `42bfd6e592f27af103eef36588a1ed8f572ceb69` ; code backend/frontend/tools identique au snapshot de régression `7b1ea54c` (diff vide, seuls docs/artefacts ultérieurs). Les tests superviseur locaux et probes possédées sont explicitement autorisés par l'utilisateur.

Préflight réel CLI/Docker/port en lecture seule à 15:23:10 UTC : trois hashes v0.2/facts exacts, Docker Linux, CLI installée présentant les huit flags requis, quatre champs d'auth `loggedIn=true`, `authMethod=claude.ai`, `apiProvider=firstParty`, `subscriptionType=team`. Aucun email/token/secret retenu. Une nouvelle vérification fraîche est obligatoire au lancement, cet état n'est pas permanent. Sonnet est configuré ; un vrai dispatch Sonnet n'est pas prouvé avant génération.

`native_supervisor_probe.py` exécuté avec Python factory-env 3.14.5, arguments `--root <integration>/Brainstorming/Autospec --expected-commit 42bfd6e592f27af103eef36588a1ed8f572ceb69 --campaign relais-support-rem25-native-supervisor-20261012-v2 --port 8131` : **rc=0 en 5,97 s**. Préflight frais à 15:26:40 UTC dans `native-probe.json`. Vrais Windows Job/Popen suspendu/venv redirector et handle d'interpréteur retenu, vrai GET santé, fermeture des ressources exactes. La création est volontairement interceptée avant son corps/POST ; les seules requêtes autorisées sont GET santé. Aucun projet, appel LLM ou coût de génération. Port 8131 fermé après cleanup ; 8126/18004 non utilisés.

Première tentative de cette nouvelle fixture : `Popen` remplacé par une fonction d'observation, ce qui casse le cold import asyncio qui en hérite. Échec avant création d'un processus factory/POST. Correction de la seule fixture : sous-classe de Popen natif, sans changement du launcher. Scope de test neuf v2 ; pas une deuxième génération.

Rapport indépendant et hashes exacts : `NATIVE-SUPERVISOR-REVIEW.md`. Le journal, l'identité factory et le reçu natif sont conservés byte-identiques. Cette preuve ne vaut ni création, ni génération, ni conformité produit, ni libération REM-24. La régression finale est encore en cours et la campagne réelle n'a pas été lancée.
