# Premier lancement REM-25 — défaut du payload de stack

Campagne unique : `workspace/relais-support-rem25-20261012-final`. Projet créé une fois : `relais-support-rem25-20261012-fi-0e6ebc49`. Fabrique propre `312cc2d38dc1a8ce7125243e4b3f36ac5ca03395`, port 8130. Préflight frais à 15:55:24 UTC le 12 octobre 2026 : Claude Code `claude.ai/firstParty/Team`, Sonnet, Linux Docker, génération seule, plafond 40 USD estimés admis. Octets v0.2 inchangés.

À 15:55:26 UTC, le vrai POST crée le projet ; le bootstrap échoue : `'Python/FastAPI' is not a valid BackendLanguage`. Phase `needs_attention`, bootstrap `failed`, aucune story/fingerprint/source livrée, **0 appel agent, 0 token, 0 USD enregistré, 0 appel non comptabilisé**. Le montant n'est pas une facture ; l'absence de dispatch est aussi attestée par les événements.

Cause : le lanceur envoyait les labels d'affichage `Python/FastAPI`, `SQLite`, `React/TypeScript/Vite` dans le contrat structuré canonique. Son test offline affirmait les mêmes labels sans composer le payload avec le vrai sélecteur. La fabrique a refusé avant source/LLM ; la campagne est non fonctionnelle à cet arrêt. La globale verte n'avait pas démontré cette composition réelle.

Régression parent : `backend/tests/test_support_campaign_payload_composition.py`, vrai payload/création ASGI/sélection de stack ; scaffold/bootstrap interceptés avant exécution produit/LLM. Initial **1 FAIL/1 PASS**, 0,89 s, rc1 : nominal reproduit l'erreur ; autre cas prouve sur fixture que PUT /language conserve ID/brief/oracle/budget/usage puis que la reprise du même projet rejoint le bootstrap canonique. Ce n'est ni une reprise effective ni une génération réussie.

Le superviseur dormant initial a été interrompu via sa session terminal possédée. Aucun reçu `SUPERVISOR_STOPPED` : ne pas inventer un finally gracieux. Lecture seule ensuite : aucun processus aux IDs possédés 21380/37428 et aucun listener 8130 ; Job Windows fermé à la sortie du superviseur. Aucun stop par nom/action sur 8126/18004/autres projets. Preuves initiales conservées byte-for-byte avant reprise.

Snapshot initial : `autospec-state.json` 23 617 octets, SHA256 `b3e78ec1f96e1d3fa2f097965099a210182d3e713735c049d6325c2cda673256` ; `build-monitor.jsonl` 806 octets, SHA256 `3ab11c157021604040b1e44fd13aa31642a5fbde408217e6c0c7abab961d91d1`. Oracle hors produit hash de contrat `b6850a3f3486afaa97816567e26ae79705464d2703ac204c0ca3440acf9e3bc6`, 67 068 octets, SHA256 du fichier `06fef2a5c08632e6dd6f398c6d54d4e8a30963055d601b5c002be83a4d0bdb80`. Aucun produit à exécuter/réparer manuellement.

Correctif attendu : contrat canonique complet et composition rouge→vert. Reprise bornée du **même** projet sans seconde création/reset de budget/modification produit, uniquement après revue indépendante/préflight frais et vérification pré-LLM/source/oracle/usage/propriété. REM-25 IN_PROGRESS ; aucun critère produit PASS annoncé.
