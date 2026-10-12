# REM-25 — qualification de la reprise pré-bootstrap

## Périmètre et état

La campagne unique `relais-support-rem25-20261012-final`, projet
`relais-support-rem25-20261012-fi-0e6ebc49`, a été créée sur `312cc2d3`.
Le payload utilisait des labels de présentation au lieu des valeurs canoniques :
`Python/FastAPI` a été refusé avant bootstrap ou appel LLM. L'incident original
reste conservé, sans réécriture du brief, du référentiel ou du budget.

Le correctif porte uniquement sur le lanceur et ses tests : payload canonique
et continuation unique, explicitement liée à cet incident pré-LLM. Il ne corrige
pas un produit généré et ne permet pas une seconde création de projet.

## Preuves déjà acquises

- Qualification générale du backend/frontend inchangés : snapshot `7b1ea54c`,
  3 232 PASS, 100 SKIP explicites, 0 FAIL/ERROR ; frontend 308 PASS/build PASS.
  Les suites ciblées ci-dessous se recouvrent avec cette globale : ne pas additionner
  leurs totaux pour annoncer un nombre de tests uniques.
- Composition API réelle du payload initial : 1 FAIL/1 PASS, rouge conservé dans
  `20261012-launch-stack-incident`. Le contrôle refusait correctement le label.
- Après correctifs `439ebcfd` et `cd3a9d90` : 115 tests auteur PASS ; contre-revue
  indépendante 122 PASS, comprenant sept contre-tests ; premier rouge 5 FAIL/2 PASS
  et second échec de décodage du harnais conservés.
- Parent sur intégration `df3aae1f` : 330 PASS, 0 SKIP, 0 FAIL/ERROR, 15,79 s.
  XML SHA256 `3adb4954dcdb4c72d64a588d9caa132303918667c00b6088b939cb0e6eccf0ac`.
- Probe natif v1 sur **copie fictive** : démarrage réel de la fabrique, Job Windows
  et handle d'interpréteur possédés ; uniquement GET health/GET projet ; rejet
  `unexpected campaign/product directory`, avant PUT/resume. Coût/appels zéro,
  bundle de campagne original intact. Ce rouge n'est pas un succès de reprise.

## Défaut natif v1 et correction requise

Le démarrage de la fabrique récupère les publications :
`server._arecover_projects` → `Pipeline.arecover_publication` →
`inspect_deployment` → `PublicationRegistry.status`. Le registre absent crée
exactement le répertoire vide
`projects/.autospec-supervisor/<id>/publication/empty-runtime-stage` et le
verrou `publication/<id>.lock`, contenant l'octet ASCII `0`. Aucun journal de
publication ni opération Docker n'en résulte pour un registre absent.

L'admission initiale doit continuer à refuser ces artefacts. Seule la vérification
après démarrage du superviseur possédé peut admettre ces chemins exacts, stage
vide et verrou d'un octet exact ; journal, contenu, autre projet, chemin inconnu,
alias/hardlink/reparse point restent refusés. L'environnement applicatif/core
n'est pas changé.

La fermeture du Job lance la terminaison des enfants, sans garantir une fermeture
synchrone du listener. Le résultat brut v1 `port_closed=false` immédiat est conservé ;
une lecture ultérieure ne trouvait plus de listener. Le harnais v2 observera la
fermeture pendant cinq secondes au maximum, sans kill par PID/nom ni assertion
affaiblie. Cela ne constitue pas une preuve de shutdown applicatif gracieux.

## Qualification finale du lanceur

Correctif auteur `54e3768b`, preuves `047e633c`, intégré avec les reçus antérieurs
dans `5d30ac826eb56484ab1dbdfc657330a9d401c577`. Seuls le lanceur et ses tests
ont changé depuis la qualification générale ; le backend/frontend reste identique
à `7b1ea54c`. Aucun nouveau replay global de trois mille tests n'a été prétendu.

- Auteur : 129 PASS/0 SKIP, 2,67 s, dont provenance Registry.status réelle sans
  appel Docker et refus des autres artefacts/types/tailles/aliases.
- Contre-revue : 145 PASS/0 SKIP, 4,08 s (129 auteur + 16 indépendants).
  `STARTUP-COW-REVIEW.md` et `independent-startup-after-v2.xml`. Pas de P0/P1
  restant reproduit dans ce périmètre. Un premier lancement des tests a rencontré
  WinError5 sur le répertoire temporaire ; le replay superviseur autorisé passe.
- Parent intégré : **344 PASS/0 SKIP, 0 FAIL/ERROR, 5,34 s**, `parent-v2.xml`,
  SHA256 `78cb44bd5af84ca26093d020eb992622fc5042e5e0478c924173bc7e73e7f654`.
- Probe natif v2 : **rc0**, fabrique et Job réels sur nouvelle copie fictive ;
  GET health/projet, **un PUT réel** language=python puis GET, **un resume
  intercepté avant transport**. Zéro POST transmis, appel LLM ou coût ; ID,
  budget40, oracle et tous les autres champs conservés. Original campagne et
  ancien runtime byte-identiques. Job/handle fermés, enfant direct rc0, listener
  fermé observé en 0,282 s. `native-copy-v2.json`, SHA256
  `a5c5362820041acd647920c9d17acdc6b88416cc6b91d5f60e8c9caf005d539d`.

Commandes parent (Python factory-env verrouillé, cwd backend d'intégration) :

```text
python -m pytest tests/test_support_benchmark_campaign.py tests/test_support_campaign_bootstrap_recovery.py tests/test_support_campaign_payload_composition.py tests/test_stack_decision_remediation.py tests/test_project_foundation.py tests/test_language_selector.py -q --basetemp <owned>/rem25-recovery-integrated-parent-v2 --junitxml <owned>/rem25-recovery-integrated-parent-v2.xml
python native_recovery_supervisor_probe.py --root <integration Autospec> --commit 5d30ac826eb56484ab1dbdfc657330a9d401c577 --fixture <owned>/native-recovery-supervisor-v2 --port 8132
```

Qualification du lanceur libérée. Restent ouverts : préflight Team frais sur
révision propre archivée, **une seule reprise du projet réel existant**, puis
génération, snapshot final et 57 critères indépendants X/R/V. REM-25 reste
IN_PROGRESS ; aucun PASS produit ni clôture de l'objectif n'est annoncé.

Le probe natif intercepte `/resume-build` **avant transport** et retourne un ACK
fictif seulement pour tester le cleanup du superviseur. Il ne prouve donc ni
génération, ni bootstrap produit, ni conformité d'un critère produit. Tout code
produit devra rester exécuté exclusivement en Docker Linux NETNONE.

Le plafond de 40 USD est une estimation de campagne, pas un cap de facturation
du provider. Génération seulement via Claude Code/Sonnet, connexion claude.ai
Team ; aucune revue des sources par Claude, API payante directe ou activation
de crédits additionnels. Proposition opérationnelle et revue indépendante restent
deux sous-agents GPT 6.1 sol medium distincts, sur paquets source exacts.
