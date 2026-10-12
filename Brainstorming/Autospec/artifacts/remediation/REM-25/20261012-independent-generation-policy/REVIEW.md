# Revue indépendante de l'admission generation-only

Cible source : `9c05c5fc89a9165e3acce42f56236b2bd1f71af3`. Source parent en
lecture seule ; nouveaux métatests et ce rapport dans le worktree de revue.
Pas de lancement, auth/CLI probe, génération, appel provider réel ou payant,
code produit hôte, edit du tableau ou des modules source du parent.

Verdict : **P1 confirmé sur rôle nommé inconnu**, refus des providers et modèles
connus favorable dans les voies examinées. Aucun P0 confirmé. Le launcher
concret n'est pas encore créé/qualifié ; ce rapport ne libère pas son démarrage.

## P1 — unknown persona hérite de l'autorité dev

`agents/personas.py:250..262` met en cache `persona(agent)` et, quand le rôle
n'a pas de fichier BMAD ni d'entrée FALLBACK_PERSONAS, retourne le prompt dev.
`agents/generation_policy.py:29..35` valide seulement l'égalité du TEXTE du
system_prompt avec les prompts admis. Le nom inconnu disparaît donc avant
la décision ; `independent-source-review-unknown` devient un dev admis lorsque
les personas intégrées sont utilisées (configuration effectivement présente
ici : `dev_file_present=False`, `unknown_is_dev=True`).

`unknown-before-v2.xml` / `.log` : **2 FAIL / 18 deselected / 0,76 s**, rc1.
Tests à invariant correct, aucun assouplissement : GENERATION_ONLY_AGENTS actif,
BMAD absent explicitement, chaque cas obtient **un dispatch FakeRunner Sonnet**
au lieu de zéro. Avec ou sans préwarming du cache lru AVANT l'activation de
campagne, le rôle nommé inconnu hérite de la même permission. Les refus
de plain-text `unknown role` du corpus parent ne couvrent pas ce chemin public.

Impact : une erreur de configuration ou un nouveau nom de rôle de revue peut
envoyer du travail de revue au fournisseur génération malgré la politique
fail-closed annoncée. Cela ne prouve PAS qu'un producteur peut choisir le
system_prompt du superviseur ni créer un rôle BMAD hors broker.

Correction proposée au coordinateur, sans édition source ici : validation du
NOM du rôle par l'API publique persona en mode campagne AVANT consultation
du cache ; comportement générique inchangé. Le préwarming reste un contre-test
obligatoire. Une identité de rôle explicite et trustée est aussi admissible.
Un acteur/code superviseur forgeant délibérément le texte connu dev relève
de la frontière de confiance, pas d'une autorité cryptographique de ce wrapper.
Une configuration BMAD trustée remplaçant des personas par du contenu arbitraire
n'est pas qualifiée par cette égalité de texte.

## Contrôles favorables reproduits offline

`junit-v1.xml` / `.log` : **89 PASS / 8,80 s**, rc0. Les 71 métatests du parent
sont repris avec 18 probes indépendants supplémentaires, avant les deux RED
ci-dessus ; aucun résultat rouge ultérieur n'est effacé ou appelé vert.

- Les SIX vrais POST ASGI `/api/provider` vers openai/openrouter/ollama/claude/
  anthropic/codex retournent422 avant tout constructeur interdit. Le runner
  courant, les pipelines et le provider de campagne restent ceux d'origine.
  Les autres providers restent accessibles en mode générique, hors campagne.
- POST vers `claude code` avec modèleopus stocke actuellement la préférence et
  retourne200, mais l'appel suivant est REFUSÉ avant activité/compteurs/CLI.
  Ce n'est pas une générationOpus : disponibilité/UI potentiellement confuse,
  mais modèle non autorisé ne s'exécute pas. Refus HTTP précoce serait une
  amélioration d'ergonomie, pas un nouvel appel autorisé.
- Cinq personas connues critic/judge/security-reviewer/evaluator/independence-judge
  ne peuvent même pas entrer dans la capability probe du vrai ClaudeCliRunner :
  `_ensure_claude_isolation` et `_run_tracked` sont des ports interdits du test.
- Six rôles qa/dev/sm/po-structure/po-spec/po-gherkin traversent le code réel
  ClaudeCliRunner avec I/O intégralement stubbé. L'argv observé porte Sonnet,
  restricted/safe-mode et tools vide, cwd d'inférence vide ; clés API et
  NODE_OPTIONS canaris ne sont pas transmis. Le résultat/coût est SCRIPTÉ,
  ce n'est pas une preuve d'inférence ni d'authentificationTeam.
- Les guards de routage rôle, _FORCE_MODEL/escalade et override direct parent
  sont rejoués ; les refus de politique sont avant journal/activité/réservation
  et ne deviennent pas une incertitude de coût ou un reçu payé.

QA admis signifie génération des tests/retour technique au dev. Cela ne
confère PAS autoritéR indépendante, verdict final ou humanwaiver. Les R réelles
restent le protocole externe GPT et les gates sur preuves exactes, pas le nomqa
ni une narration du modèle. Les lectures de code nécessaires à la génération
ne sont pas reclassées silencieusement en revue indépendante.

## Composition du futur launcher à vérifier

- GEN flag actif AVANT import du serveur/création `_runner`, ou runner recréé
  via `make_runner` sous ce flag puis type GenerationOnlyRunner vérifié. Un
  changement de flag après création ne wrappe pas rétroactivement un runner
  brut ; `_UsageTracker` n'appelle validate_call que s'il existe. Le launcher
  absent n'est pas présumé correct sur ce point. Les constructions/injections
  de runner sont des opérations trustées, pas des outils du producteur.
- make_runner doit construire l'inner ClaudeCliRunner, pas un API runner
  enfermé manuellement dans le wrapper ; injection FakeRunner seulement pour
  les métatests. PréflightTeam/firstParty fresh, sans credential copiée.
- CLAUDE_MODEL=sonnet ; routage/phase/tier tous compatiblesSonnet,
  ESCALATE_ON_RETRY OFF. REFINE/SECURITY_REVIEW/EVALUATOR/INDEPENDENCE/LANGFUSE
  OFF et admission de rôle mécanique malgré endpointforce. FAKE_AGENTS OFF.
- Même brief/faits/57 IDs, sept lots ; nouveau run40USD estimés sérialisés,
  coût incomplet reste bloquant ; pas de cap de facturation dur revendiqué.
- Launcher source/SHA + ports concrets + suites de garde avant tout démarrage.
  Le reste du plan de lecture est dans `independent-launcher-preflight-plan.md`.

L'inventaire statique de capacités n'instancie pas de provider, mais n'est
pas une permission d'emploi. La route de découverte de modèles générique
peut appeler des APIs metadata si des clés sont configurées ; elle n'a pas
été invoquée ici et ne constitue pas une preuve de générationAPI. Le launcher
doit conserver l'environnement campagne sans clés/API supplémentaires.

## Provenance

SHA256 des sources parent lues, octets Windows (aucun diff source de revue) :

- generation_policy : `31a0c7885bc2ef2dc5ec2396a66628ce0856a8052628307f11990617e52f8177`.
- providers : `2ba24ccc26b8fe8ece4ff6e62f208e3dc69bf97ab3401221535ab768f84fc01a`.
- pipeline : `bdba73fe937cd6d5b34438fe3f5ee5236e6533545378a07b4f3718d5a182d93b`.
- tests parent generation_only : `f4afe9b19da6e522612b007a9da7e0994d59585307cefeedb0f13f0908039df8`.
- personas public : `84e2dc4627e1f9b8b983749b3079bd1b1fad9b43dee4372e97c01b4b7f67918c`.
- contre-tests finaux (incluant RED) : `16412c51cf056f8926650c53b4bfde31ad8e95579fe3eb21fa796858f92bb7b2`.
- XML 89 PASS : `5dcb4cec721a4af20ac321ca8e2ec288c42ad797031a91e5cf1cbb22658b7849`.
- XML unknown RED : `20660bfaadf3651ac57823264e7c8e6e4f06a1d8bfe9c63b46ecc23cab074274`.

Le parent prépare la correction persona publique après réception de ce RED.
Un replay AFTER sur son SHA est nécessaire ; aucune source de cette cible
ni preuve précédente n'a été réécrite pour faire passer le contre-exemple.
