# Interfaces de remédiation Autospec — REM-00

11 octobre 2026. Contrats minimaux pour les lots parallèles. Le code existant reste la base ; les agents ajoutent des modules spécialisés et proposent leurs raccordements au coordinateur.

## Propriété de l'intégration

Le coordinateur détient `pipeline.py`, `prompts.py`, `models.py`, les types partagés et le tableau REM. Les agents n'éditent pas ces fichiers sans attribution explicite. Les nouveaux modules sont importables sans Docker ni provider disponible ; les opérations externes sont derrière une interface injectable pour les tests. Chaque lot fournit les points d'appel nécessaires et des tests de comportement négatif.

## Exécution et ressources possédées

Version de contrat : 1. Un contexte d'exécution identifie `run_id`, racine du projet résolue, backend de confinement et ressources possédées. Ressource : type, identifiant, identité de création et propriétaire. Le contexte ne contient aucune credential sérialisable. Le confinement du harness est différent du nettoyage de ses descendants ; un Job Windows ne protège pas l'hôte contre les commandes d'un agent privilégié.

Exemple d'entrée : `{ "version": 1, "run_id": "run-demo", "project_root": "<absolute isolated path>", "backend": "restricted_tools" }`.
Exemple de sortie : `{ "status": "ready", "capabilities": ["read_project", "write_project"], "host_shell": false }`.
Backend indisponible ou incapable de garantir les capacités : échec `ISOLATION_UNAVAILABLE`, jamais fallback non signalé. Les droits d'accès aux manifests et aux oracles sont distincts. Les identités de processus sont détenues par le superviseur et vérifiées avant terminaison.

## Dépendances et environnement

Une demande identifie `task_id`, écosystème, paquet, contrainte, portée runtime/dev, motifs et fichiers manifest/lock canoniques. Validation et intégration sous verrou de manifest ; état `pending`, `applied` ou `rejected`, avec motif. Une tâche ne devient pas GREEN sur une demande pending.

Exemple : `{ "version": 1, "task_id": "AUTH-1", "ecosystem": "python", "package": "argon2-cffi", "scope": "runtime", "constraint": ">=23", "manifest": "pyproject.toml", "lock": "uv.lock" }`.
Empreinte d'environnement : manifest + lock + version outil + plateforme + mode runtime/tests. Cache réutilisable seulement si empreinte identique et création propre attestée. Un import installé localement hors manifeste n'est pas une preuve.

## Claims et plan

Claim : chemin relatif canonique POSIX, racine de stream résolue, propriétaire de tâche, mode exclusif ou lecture, et motif. Refuser chemins absolus, traversal et racines incompatibles ; traiter la casse selon la plateforme. Exemples : `relais_support/db.py` à racine vide ; `frontend/src/auth/**` pour stream frontend. Un fichier futur valide n'a pas besoin d'exister.

L'élargissement est arbitré avant écriture ; conflit avec un propriétaire actif = attente/arbitrage explicite. Les fichiers de contrat commun erreurs/horloge/DB ont un propriétaire préalable et des dépendances de plan.

## Contrat d'acceptance et preuves

Contrat immuable versionné : hashes du brief/référentiel, exigences `{id, gate, expected, required_evidence}`, contraintes techniques et scénarios. L'oracle est stocké hors racine accessible en écriture au produit. Aucun changement d'attendu déduit du code livré.

Résultat : `{ "version": 1, "contract_hash": "<sha256>", "snapshot_hash": "<sha256>", "status": "fail", "requirements": [{ "id": "SEC-03", "status": "FAIL", "evidence": [{ "type": "X", "path": "<artifact>", "detail": "real hasher missing" }] }] }`.

Statuts requirement : PASS/FAIL/NOT_VERIFIED/BLOCKED_ENV/NOT_APPLICABLE selon le référentiel. Statut de gate : pass/fail/not_verified. PASS exige les preuves requises, une identité d'artefact et aucun ID manquant/doublon ; N/A interdit pour B/M applicables. Une tâche DONE et un HTTP health 200 n'établissent pas la conformité. Une nouvelle révision invalide les preuves incompatibles. Aucun secret brut dans les artefacts.

## Événements et état durable

Événement : version, run_id, task_id si applicable, phase, raison d'attente, timestamps UTC, durée, appel provider actif, consommation enregistrée, réserve et coût incomplet. Phases attendues : waiting_dependency/waiting_claim/waiting_budget/provider/tests/merge/repair/interrupted/completed. `completed` génération, déploiement et acceptance restent distincts.

Exemple : `{ "version": 1, "run_id": "run-demo", "task_id": "AUTH-2", "phase": "waiting_budget", "owner": "AUTH-1", "active_provider_calls": 1, "cost_incomplete": false }`.
L'état durable conserve identité du worker, dernier jalon et motif d'interruption. Réconciliation au redémarrage sans lancement LLM automatique. Aucun montant estimé ne devient une facture affichée.

## Adaptation et validation REM-00

Les nouvelles données sont des sidecars versionnés ou des champs optionnels compatibles ; loader ancien état accepté. Les modules spécialisés restent responsables de la validation de leurs objets, le coordinateur de leurs raccordements. Exemples ci-dessus couvrent entrée/sortie et échecs ; les tests exécutables sont remis dans chaque lot. Ce contrat est gelé pour la première vague, changement coordonné et journalisé si nécessaire.
