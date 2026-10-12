# AFTER indépendant — garde des noms avant cache

Cible exacte : `a79ce3b907948dcecf855fec176864320a99f10a`, intégrée dans le
worktree de revue propre. Aucun changement aux sources du parent ni aux
contre-tests. Le correctif est du parent ; cette preuve demeure indépendante.

Verdict ciblé : **P1 unknown persona résolu dans les voies reproduites**.
`agents/personas.py:265` valide désormais le NOM en mode campagne avant
`_cached_persona`, même si le prompt inconnu a été préchauffé en mode générique.
Les rôles source-review connus sont aussi refusés avant cache et avant CLI.
Le comportement générique intentionnel n'est pas supprimé.

## Résultats et reproduction offline

`after-v1.xml` / `.log` : **91 PASS, 0 FAIL, 0 SKIP, 1,65 s, rc0**.
Six modules, les mêmes 89 IDs qu'avant plus les deux contre-exemples RED
inchangés (`prewarm=False` et `True`). Aucune disparition/renommage parmi les
89 IDs historiques. Les 95 PASS du parent couvrent un corpus distinct ; ils
ne sont pas revendiqués comme ce replay indépendant.

Depuis `backend` du worktree de revue, avec le Python verrouillé
`C:/Dev/squad-ai/Brainstorming/Autospec/workspace/remediation-20261011/factory-env/Scripts/python.exe` :

```text
python -m pytest tests/test_generation_only_policy.py
  tests/test_generation_policy_counterreview.py tests/test_providers.py
  tests/test_api_provider.py tests/test_anthropic_provider.py
  tests/test_rem24_budget_and_cache_counterreview.py -q --tb=short
  --basetemp=C:/Dev/squad-ai/Brainstorming/Autospec/workspace/remediation-20261011/generation-policy-after-v1
  --junitxml=../artifacts/remediation/REM-25/20261012-independent-generation-policy/after-v1.xml
```

Les variables de probes réelles Claude/Linux/Docker/browser sont à OFF.
Les ports d'inférence/auth/CLI sont stubbés ou interdits dans les métatests,
pas invoqués réellement. Les appels API sont ASGI locaux ; les coûts simulés
ne prouvent ni une facture ni une authentification Team. Pas de lancement,
code produit hôte, génération, appel payant, modification du tableau partagé
ou snapshot historique.

`compatibility-after-v1.log` : cinq assertions mécaniques supplémentaires,
rc0 (pas cinq tests pytest ajoutés) :

- BMAD explicitement absent, le rôle inconnu générique retourne toujours dev.
- Après préwarming puis activation, tous les noms de revue de FALLBACK_PERSONAS
  et le nom inconnu sont refusés avec code GENERATION_ONLY et usage_reported=True.
  Chaque refus laisse `cache_info()` rigoureusement inchangé.
- Le rôle dev autorisé réutilise le cache existant.
- Le passage retour au mode générique conserve le fallback sans vider le cache.
- Les API publiques `cache_clear` et `cache_info` restent fonctionnelles.

Ce probe importe uniquement le code superviseur et utilise un répertoire
temporaire possédé avec BMAD absent. Il restaure les settings et vide le cache
en finally. Aucun port provider, CLI ou auth n'est présent dans ce probe.

## Limites et prochaine admission

L'égalité des textes du wrapper ne prétend toujours pas empêcher un code
superviseur trusté de forger volontairement un prompt dev connu. Elle ne
qualifie pas non plus un fichier BMAD arbitraire installé par le superviseur.
Le fix empêche l'erreur de configuration publique unknown→dev, pas une fausse
autorité cryptographique. QA reste génération de tests/retour technique,
jamais R indépendante ou permission de shipping.

Le launcher concret n'est pas encore fourni : **aucune autorisation de
démarrage**. Sa composition devra activer GENERATION_ONLY_AGENTS et les OFF
de revue/télémétrie avant import/création `_runner`, construire réellement le
wrapper via make_runner, imposer Sonnet à tous routages et exclure les clés
API. Un flag activé après construction ne rétrofitte pas un runner brut.
Le préflight Team réel et le lancement sont hors périmètre de ce replay.

Les contrôles provider/modèle et le vrai refus de contexte stale/budget
non réconcilié des sept contre-tests REM-24 passent dans les 91. Ce replay
ciblé ne rerun pas le corpus superviseur277 ni la validation native finale.
Les quatre SKIP de ce corpus restent des SKIP, pas requalifiés ici.

## Empreintes SHA256

Sources parent lues, identiques avant/après le replay (aucun diff source) :

- personas : `fb8c9c9eada05783126cdfe5b59a269ce61e53971b77ec623426c1b9611512c5`.
- generation_policy : `31a0c7885bc2ef2dc5ec2396a66628ce0856a8052628307f11990617e52f8177`.
- providers : `2ba24ccc26b8fe8ece4ff6e62f208e3dc69bf97ab3401221535ab768f84fc01a`.
- pipeline : `1e94fd781e53143dbbd1834b4f53a147163f19abb066bcda3ee87bd2fe8e661f`.
- contre-tests inchangés : `16412c51cf056f8926650c53b4bfde31ad8e95579fe3eb21fa796858f92bb7b2`.
- AFTER XML : `81726618b71a7a0edea12461bf4d075985ccfbaba20b611acb00bba1eaf50d9d`.
- AFTER log : `3b94430b5a83e083b3086db6417f78e61bd3ef53146a0422959781301d11d5b6`.
- compatibilité log : `9d5b2bf5cd43ae0faf17734da7e87d09a63f3b7224d4de3232683ce12b771cc8`.

Les deux FAIL historiques restent dans `unknown-before-v2.xml` et `.log` ;
ce document n'en modifie ni la source ni la preuve.
