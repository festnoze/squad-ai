# REM-14 / REM-20 / REM-21 — harnais natif et raccord

Ce paquet prouve le **mécanisme de validation sur une fixture indépendante minimale**, pas l'acceptation 57/57 du benchmark. Le snapshot de cette fixture est `f1dbddc3d00f8104ceec79fe6acefbf64934128d79c2cbe4602bdfe351acf866` ; le hash de contrat de métatest est `cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc`. Ces identités ne sont jamais substituées au contrat produit réel.

Sources : checkpoint `2f600d0b56a1b09f3f8d74e968fbc6f6ec4674ce`, correctifs/raccord `6644e03d`. APIs navigateur/qualité des commits pairs `c96ece12`, `4d4142b5`, `252f0407`. [bindings.md](bindings.md) décrit les signatures et la publication revue exacte.

## Résultats retenus du 12 octobre 2026

| Campagne | Résultat | Preuve et portée |
| --- | --- | --- |
| run10 globale retenue | 26 PASS / 3 FAIL, 16681.24 s | `pytest.log`, `junit.xml` : trois échecs Docker init/readiness/cleanup pendant les longues suspensions d'outils. Pas de PASS global ; pas d'attribution démontrée à une assertion métier. |
| run11 OPS ciblée | 1 FAIL, 144.04 s | `ops-native-pytest.log`, `ops-native-junit.xml` : positif baked/vertical/persistance obtenu puis une course du harnais au redéploiement du contre-exemple. Corrigée par attente HTTP GET-only, jamais retry de mutation. |
| run12 OPS + API publique coordinator | 2 PASS, 185.29 s | `ops-verified-pytest.log`, `ops-verified-junit.xml`, `evidence/baked`, `evidence/lost_note`, `evidence/reset_on_start`. Image immuable sans montage source ; Argon2id réel ; Chromium/TCP HTTP ; DB/audit committés ; vrai restart et detach/attach du volume ; trois replays HTTP200 mêmes IDs sans écriture. Les deux sujets délibérément fautifs donnent FAIL natif. |
| run13 port SQLite qualité | 1 PASS, 39.74 s | `sqlite-quality-pytest.log`, `sqlite-quality-junit.xml`, `evidence/sqlite_quality`. Connexions applicatives réellement distinctes, export SQLite exact privé, vraie comparaison API/DB après restart, conteneur et volume exacts absents après fermeture. |
| Régressions harness/coordinator/architecture/qualité | 44 PASS / 12 SKIP, 101.59 s | Les 12 skips sont les tests Linux/Chromium explicitement opt-in, exécutés dans les campagnes natives séparées. Aucun test critique du produit n'est converti en skip. |

Les reçus principaux `evidence/baked/{receipt,image,persistence,ops04}.json` référencent leurs vrais fichiers X/V conservés octet pour octet. `lost_note/ops04.json` contient `initial_records_committed=false` ; `reset_on_start/ops04.json` contient `lifecycle_rows_preserved=false`. Ces contradictions observées restent FAIL, même si la suppression des comptes rendrait ensuite une authentification impossible. Les replays downstream ne sont pas déclarés exécutés après ces contradictions.

Les deux générations de reçus baked sont conservées (run11 et run12) ; les fichiers principaux désignent run12. Les preuves natives SQLite conservent le chemin de l'export privé observé pendant run13. **Aucune base, cookie, session, mot de passe ou fixture de credentials n'est incluse dans ce bundle.** Les schémas, nombres de lignes et digests de DB ne contiennent pas les valeurs des sessions.

## Reproduction

Depuis `backend` avec le Python factory verrouillé :

```powershell
$env:AUTOSPEC_REAL_PRODUCT_HARNESS='1'
& 'C:/Dev/squad-ai/Brainstorming/Autospec/workspace/remediation-20261011/factory-env/Scripts/python.exe' -m pytest tests/test_product_harness.py tests/test_validation_coordinator.py tests/test_architecture_contracts.py -q
```

Docker Linux et Chromium sont obligatoires pour ce mode. Pas d'import de code produit sur l'hôte, d'ASGI transport nominal, de session injectée ni d'appel LLM payant. Seuls conteneurs/volumes/UUID possédés sont nettoyés ; aucun prune/reset global.

## Limites ouvertes

- Les R du produit réel doivent être issus de la revue indépendante locale demandée ; aucune R positive n'est fabriquée par le harnais ou le contenu de la fixture.
- La campagne complète exige les cas/variantes de fixtures et sélecteurs UI exacts, bindings clock/fault/race source-revus et les observations natives suites/coverage/audit/build. Une absence donne NOT_VERIFIED.
- L'instrumentation diagnostique Python/ASGI/SQLite est séparée de l'image finale directe. Elle n'est pas une enclave protégeant l'interpréteur contre l'introspection d'un produit hostile ; non-SQLite, drivers personnalisés ou symboles absents restent indisponibles.
- Les IP alternatives sont prouvées via sockets Linux au noyau, sans X-Forwarded-For ; les IP publiques alternatives Windows ne sont pas vérifiées.
- Les contrôles vertical et persistence ne remplacent jamais les packs SEC/FUN/ARC/UX/TST ni la revue docs/audit complète OPS-05. Le raccord NativeQualityCollector et les reçus de build natifs demeurent à installer par le parent.
