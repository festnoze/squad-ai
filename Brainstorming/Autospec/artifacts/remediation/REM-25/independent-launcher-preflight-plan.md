# Préparation de contre-revue du launcher — pas un lancement

12 octobre 2026, cible préparatoire 88b79de1 puis admission 9c05c5fc et fix a79ce3b9. Aucune création de campagne,
pipeline.start, runner.arun, providerCLI, test/init/auth réseau ou génération
n'est exécutée par ce document. Le wrapper generation-only est maintenant
présent dans 9c05c5fc. Le P1 unknown persona de la contre-revue indépendante
est corrigé dans a79ce3b9 : AFTER 91 PASS, deux RED inchangés désormais PASS,
fallback générique et garde avant cache également vérifiés offline. Le launcher
concret reste absent ; son chemin/SHA final devra être fourni pour une revue
indépendante et les contre-tests offline avant démarrage.

## Prérequis d'admission à relire

1. Révision factory effectivement chargée = commit qualifié stable ; reprise
   dans un processus frais si les fichiers du moteur ont changé. Préserver
   l'arbre utilisateur et le snapshot support20261008 en lecture seule.
2. Même source v0.2 : briefSHA256
   `0a99950df5ee132253fa5aefb1a8f6e4f7a4b64c1436072564be6d28195fb0f3`,
   référentielSHA256
   `efdab8ea54208557f01abcb5324172e42b9c5cf88536611d64ba65b92564cbf4`,
   quatre faits source-only approuvésSHA256
   `f2b3105f207cdf4d2feb7219535146e6890d838c7b4a93a4975c6ded040644b9`.
   Le launcher ne redéduit aucune attente depuis le futur code ;57IDs exacts,
  56mandatory et OPS06 diagnostic ; max_lots strict7, pas7tâches.
3. ClaudeCode abonnement claude.ai Team, fournisseurfirstParty, Sonnet exact,
   aucun API/crédit supplémentaire. Un état auth daté doit être obtenu par le
   superviseur sans sérialiser credentials. Le runner filtre les clés API de
   son environnement, mais ses flags seuls ne prouvent pas l'abonnementTeam.
4. Modèle imposé au wrapper à chaque appel ; prévenir override model du caller,
   routage phase/tier et escalation. Une simple CLAUDE_MODEL=sonnet ne suffit
   pas si MODEL_BUILD/MODEL_CHECKER ou _FORCE_MODEL la remplacent.
   Le wrapper exige exactement Sonnet et refuse ces écarts ; le launcher doit
   mettre tous les routages sur Sonnet ou les désactiver pour rester nominal.
   Activer GENERATION_ONLY_AGENTS avant construction/import du runner, recréer
   via make_runner et vérifier GenerationOnlyRunner ; FAKE_AGENTS doit être OFF.
5. Cap nouveau run40USD estimés, distinct de l'ancien coût historique incomplet ;
   sérialisation, REM23OFF, réserves/coût connu/inconnu durables, aucun reset
   de journal pour contourner COST_UNREPORTED. Ne pas affirmer un hard cap de
   facturationClaude à partir du flagmax-budget-usd.
6. REFINE/SECURITY_REVIEW/EVALUATOR/INDEPENDENCE/LANGFUSE OFF, et surtout admission de rôle
   génération-seule AVANT touteCLI : critic/judge/security-reviewer/evaluator
   refusés même si flag/endpointforce. qa/dev/dev-frontend/PO et autres rôles de
   génération explicitement nécessaires restent autorisés. Rôle inconnu ou
   absent ambigu ne doit pas devenir une permission par défaut. La politique
   campagne ne supprime pas les capacités génériques des autres projets.
7. Deux agentsGPT distincts en modèle/raisonnement autorisés pour proposition
   opérationnelle et R indépendante ; requêtes locales request_hash/stage/phase/
   snapshot/contrat exacts. Leur output ne peut produireX/V ni humanwaiver.
   Audit raw avant revue ; bindings/fixtures/qualité/docs approuvés au sujet exact.
8. Broker/claims, WindowsJobs, LinuxNETNONE et DockerBrowser obligatoires ; pas
   de shell, import produit ou navigateur hôte. Env/cache/locks propres et
   installnetwork séparée sans scripts/credentials/source producteur.

## Graph d'appels attendu à inspecter, sans l'invoquer

Préflight trusté → import/store contrat immuable → nouveau run possédé →
Pipeline avec wrapper generation-only → génération du socle → tests natifs
confinés → plan source-admis/fondation → première tranche freeze+reviewGPT →
navigateur/login/API/DB natifs → descendants débloqués → snapshot final →
audit raw → reviewGPT qualité/livraison → construction image CMD exact baked →
collecte native suites/coverage/12E2E/mutation/docs → SEC/FUN/ARC/UX/TST/OPS →
admission finaleX/R/V mêmesidentités → publication seulement image qualifiée.

Après arrêt : coût incomplet ou NV/PASS partiel reste bloquant ; pas de boucle
payante réparant les ports manquants ; nettoyage uniquement ressources de la
campagne après re-attestation, volume utilisateur/historique conservé. Comparaison
indépendante56mandatory/57IDs sur son nouveau snapshot, sans retouche manuelle
du résultat entre génération et verdict.

Contre-tests wrapper demandés avant approbation : chaque rôle interdit via
prompt persona réel et flag/force est refusé sans CLI ; modèle différent/key
API ignorés ou refusés ; nominal qa/dev/PO conserve médiation et budget ;
inconnu/COST_UNREPORTED bloque ; cancellation/checkpoint échoué ne dispatchent
pas ; la revue externe n'appelle jamais le runner de génération. Ce sont des
tests superviseur/FakeCLI, aucune inférence réelle pour valider ce mécanisme.

État : préparation seulement. Le coordinateur fournit le launcher final,
ses appels réels et ses preuves ; aucune permission de démarrage n'est donnée ici.
