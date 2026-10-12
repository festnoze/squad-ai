# Replay Host et nouveau P1 nominal à froid

Cible parent en lecture seule : `96af8140ab8886c07936576344f36039dc0d6434`,
qui inclut le fix persona a79ce3b9 et le nouveau control_boundary. Le commit
test-only `da81d5904b650fd4caf4109382a75ef472d65452` modifie exactement les
DEUX `base_url` de test de `http://offline.test` vers `http://127.0.0.1`.
Aucune assertion, persona, wrapper, runner ou contre-test unknown n'est modifié.
Pas d'exception de production ajoutée à la frontière Host.

## Faits exécutés offline

- `origin-before-v2.xml` : **8 FAIL / 12 PASS / 1,23 s**, rc1. Sept FAIL sont
  des 403 Host attendus avant d'atteindre les assertions provider (422/200) ;
  le huitième est le vrai échec QA à cache froid décrit ci-dessous.
- `origin-after-v2.xml` : **20 PASS / 1,30 s**, rc0, même module et IDs.
  Les six switches API atteignent la vraie route puis la garde campagne422,
  les constructeurs interdits restant inaccessibles. Le transport ASGI reste
  local sans socket réseau, et les assertions de politique restent identiques.
- `after-v2.xml` : **91 PASS / 3,06 s**, rc0, les six mêmes modules de AFTER.md.
  Cela ne clôt pas le défaut sensible à l'ordre du cache.
- `cold-qa-v2.xml` : **1 FAIL / 1,75 s**, rc1, le cas nominal EXISTANT lancé
  SEUL dans un processus pytest neuf. Ses assertions/I/O stubbés sont inchangés.

## P1 — première génération normale refusée par le cache de routage

`orchestrator/pipeline.py:664..668` initialise `_PERSONA_BY_PROMPT` à partir
de TOUTES les entrées FALLBACK_PERSONAS via la fonction publique persona.
Quand GENERATION_ONLY_AGENTS est déjà actif, persona refuse mécaniquement les
noms de revue avant cache. La recherche du rôle du premier prompt QA autorisé
consulte donc également un nom de revue interdit et lève GENERATION_ONLY.

Chemin exact : `_UsageTracker.arun:715..718` → `_persona_role:667` →
`agents/personas.py:272`. Le rôle réellement demandé est bien `qa`, pas une
revue cachée. Le provider n'est pas entré : défaut de disponibilité nominale,
pas un contournement d'autorité ni un appel payé.

Le remplissage de `_PERSONA_BY_PROMPT` est progressif. Après l'exception,
plusieurs entrées restent dans la map, donc le garde `if not map` ne retente
plus son remplissage complet. Dans le module20, le négatif endpoint modèle
Opus rencontre ce refus générique et son `pytest.raises(GENERATION_ONLY)`
l'accepte ; il préchauffe involontairement la map partielle. Le nominal QA
suivant peut alors passer. Dans le corpus91, d'autres probes préchauffent aussi
la map hors campagne. Aucun de ces verts ne prouve le premier appel nominal.

Reproduction identique au test existant (variables de probes réelles OFF) :

```text
python -m pytest
  tests/test_generation_policy_counterreview.py::test_real_runner_argv_shape_pins_sonnet_and_excludes_api_keys[qa]
  -q --tb=short
  --basetemp=C:/Dev/squad-ai/Brainstorming/Autospec/workspace/remediation-20261011/generation-policy-cold-qa-v2
  --junitxml=../artifacts/remediation/REM-25/20261012-independent-generation-policy/cold-qa-v2.xml
```

Python verrouillé et contexte backend comme dans AFTER.md. Aucun lancement,
auth, CLI probe/inférence, génération ou provider réel. Le vrai objet runner
est testé avec ses ports `_ensure_claude_isolation`/`_run_tracked` stubbés ;
le défaut survient avant ces ports. Aucun code produit hôte ou snapshot édité.

## Proposition au propriétaire, sans correction source ici

Ne pas contourner le refus public persona pour construire l'index. En campagne,
indexer uniquement GENERATION_ROLES. Construire dans une map locale puis
publier atomiquement après succès ; ne pas conserver une map partielle sur
exception. L'index doit être contextuel au mode campagne/générique (ou résolu
sans cache global partagé), afin qu'un préwarming hors campagne n'en masque
pas le chemin normal. Préserver le comportement générique voulu.

Tests de garde à ajouter par le propriétaire : premier QA/dev/PO autorisé
après activation avec index vide ; passage générique→campagne→générique ;
aucune publication partielle si une persona échoue ; modèle Opus refusé par
la raison modèle attendue, pas une exception étrangère au test. Un modèle
explicitement fourni court-circuite l'appel précoce de routing, mais `_arun`
appelle encore `_persona_role:919` : ce n'est pas une solution au défaut.

**Démarrage non qualifié tant que le cold nominal n'est pas passé après fix.**
Le P1 unknown→dev précédent reste corrigé ; ce P1 est une interaction nouvelle
entre ce fix et le cache de routage préexistant. Parent informé, pipeline non édité.

## SHA256

- Source pipeline : `1e94fd781e53143dbbd1834b4f53a147163f19abb066bcda3ee87bd2fe8e661f`.
- Source personas : `fb8c9c9eada05783126cdfe5b59a269ce61e53971b77ec623426c1b9611512c5`.
- Source control_boundary : `19c1a073297971b8acebaa79f3956ad25f1d310817c3cc88f3d6ec216c594901`.
- Source server : `d36601ddfadc9db56e7710aeeb950a83f82c892a28793d32b6ce1f4b0c6943ff`.
- Contre-tests après deuxURLs : `a50ab07b73fea76acf60ff514ae2d15e3f095c94a2bf011846f90f7116c6ffbb`.
- XML before Host : `e6296e158977c9e20bce9a6abc65a2bdaa11aa78789c42016bae0e0a4cff4e41`.
- XML after Host : `f99b63745575a52a62764d84d398886745bc16a54bb2bef5b74606db5795c520`.
- XML after91 : `a1c0bb4b74434afb5964497a20274565215b3527ebb70ef20d1b3f81e9b4e22e`.
- XML cold QA : `fd7189cf908a15c461712da18e6e254f6856467b62b901b2d0e3a1d3de649bd1`.
- Log cold QA : `5e7b1d5c20e0820cc93b0412ab0bf1a2b9e42a097b00e8323bf9cd706e7624b5`.

Les FAIL sont conservés dans leurs fichiers propres, sans requalification.
