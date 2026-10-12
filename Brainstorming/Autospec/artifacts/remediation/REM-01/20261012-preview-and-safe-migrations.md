# Aperçu local et migrations des probes legacy — 2026-10-12

Base intégrée : `83605b1b`. Le parent garde les raccords pipeline/config/admission; seuls product_launch.py et les sept fichiers de tests attribués ont été modifiés ici.

## Correctif aperçu

`open_preview(..., readiness_path='/')` configure désormais `RuntimeSession(application_origin=True, local_cookie_mode=True)` : APP_ORIGIN est l'origine exacte du proxy allouée avant lancement; le mode cookie non-Secure est explicitement réservé à cet aperçu HTTP local. Aucune variable d'environnement arbitraire de produit n'est relayée. La cible readiness est un chemin factory same-origin, sans URL externe, segments `..` ou contrôle. Le statut doit être 2xx, pas une redirection, 403, 404 ou 500. Un profil API sans root doit fournir un endpoint readiness source-revu, par exemple `/api/health`, sinon l'aperçu échoue honnêtement.

La fixture réelle standard-library est exécutée uniquement dans Docker : GET formulaire/cookie HttpOnly SameSite, POST avec Origin exact + cookie + CSRF accepte200; Origin étranger ou CSRF absent refuse403. Rootfs readonly et réseau none inspectés. Fermeture révoque la liveness. Cela prouve le transport du preview, pas les critères métier/SEC d'un produit final : les gates vertical/final indépendants restent inchangés.

## Tests legacy migrés

- Codex non qualifié refuse ISOLATION_UNAVAILABLE avant tout spawn, même options model/session; parsing JSONL et discovery mockés restent testés.
- Setup ignore le vieux host argv et délègue ensure_lock/prepare Linux sans env de credentials; erreur d'isolation n'autorise aucun fallback.
- Sandbox : paramètres nonroot/readonly/capsdrop/no-new-privileges/net-none/allowlist env exacts; ancien chemin optionnel refusé avec flag ON et OFF.
- Session monitor : stop/timer/reprise/annulation/recovery vérifiés directement, sans faux DONE tiré d'un fake green produit.
- W7 evaluator : délégation exacte vers verify_runtime, aucune exécution main.py hôte ni sweep de port/PID. Une fausse structure PID-live, même PID du test, est refusée.
- W8 CLI/help : run_captured isolé exact, stdout-only requis, timeout/infra non vert et aucun host fallback; ancien argv/env help ignorés.
- Les probes de processus natifs source-revus restent réels : timeout, root sortant avec tube hérité, descendants fermés via ownership/Job, sentinelle étrangère vivante, flux stdout/stderr bornés. Aucun taskkill par PID. Le probe à trois générations garde marker+death obligatoires avec15s de startup au lieu5s, car trois redirectors venv Windows sous charge peuvent expirer avant naissance du descendant; tous dorment60s.

## Résultats

`AUTOSPEC_REAL_LINUX_VALIDATION=1 pytest tests/test_codex_and_discovery.py tests/test_setup_security.py tests/test_sandbox.py tests/test_runner_processes.py tests/test_session_monitor.py tests/test_wave7_evaluator_tree_kill.py tests/test_wave8_smoke_cli_tree_kill.py tests/test_product_launch_isolation.py tests/test_budget_tracker_reservations.py tests/test_budget_reservations.py -q --junitxml=../artifacts/remediation/REM-01/20261012-preview-legacy-native.xml` : **120 PASS / 66.81s**, aucun SKIP sur ce corpus. Le rapport JUnit est conservé. Premier passage sans opt-in :119PASS/1SKIP47.30s; preuve preview seule15PASS23.24s.

Essais initiaux non masqués : une assertion security-opt sans `=true`, une assertion trop forte « aucun env » au lieu de la allowlist HOME/PYTHONDONTWRITEBYTECODE, le descendant non né dans5s, puis huit assertions de fixture Wave8 confondant le répertoire tmp test et le root produit. Correctifs limités aux valeurs exactes/fixture et budget de startup, sans retirer les assertions de confinement ou cleanup.

REM23 contre-revu après raccord : enveloppe réservée conservée par _arun, OFF/registry vide par défaut, journal connu ignoré au restart détecté puis corrigé parent (`83605b1b`) : OFF/provider absent/token-only ne contourne plus une entrée inconnue. Tests du raccord et du journal inclus dans les120PASS. Aucune garantie hard-billing de Claude réelle n'est déclarée; les deux FakeCLI parallèles réellement lancés prouvent seulement leur plafond fake/offline. Un cap différent au restart peut bloquer CAP_UPDATE_REQUIRED : limite failclosed visible, jamais coûts effacés.

Aucun code produit sur l'hôte, aucune API payante. La régression globale initiale1998PASS/59FAIL/41SKIP reste distincte; ce lot ne prétend pas rendre les26 tâches DONE ni prouver tous les critères du support-client.
