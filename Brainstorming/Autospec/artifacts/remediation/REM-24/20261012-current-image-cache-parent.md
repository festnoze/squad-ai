# Admission actuelle de l'image — correctif parent

Le contre-test indépendant livré par `rem_execution` est inchangé : ses quatre variantes refusaient l'absence ou le changement du CMD de l'image sur des contrats OPS-01 seul et OPS-01+OPS-05. Avant correction, le port d'attestation n'était jamais appelé et le cache historique suffisait à rendre la livraison READY.

Le raccord parent appelle maintenant `load_qualified_delivery_image` avant READY pour tout contrat possédant OPS-01, OPS-02, OPS-03 ou OPS-04, y compris lorsque la publication Docker est désactivée. Ce port relit les rapports, les bindings et le reçu natif, puis inspecte l'image exacte et son CMD ; il n'a pas le droit de reconstruire ou réparer. Un artefact absent ou invalide donne NOT_VERIFIED actuel et conserve les preuves historiques.

Preuves :

- `current-image-cache-parent-v1.xml` : 43 PASS, 3,66 s, dont les quatre contre-tests inchangés.
- `current-image-cache-parent-v2.xml` : 43 PASS / 5 FAIL, 13,75 s. Les cinq nouvelles fixtures nominales comparaient à tort l'identité Python d'un contrat relu depuis le store ; le hash immuable, pas l'adresse de l'objet, est l'identité attendue.
- `current-image-cache-parent-v3.xml` : 48 PASS, 4,95 s. Les cinq fixtures nominales supplémentaires vérifient l'attestation de l'image après collecte fraîche et après réutilisation, tout en gardant les contre-tests adverses inchangés.
- `generation-image-policy-parent-v1.xml` : 92 PASS, 4,68 s, corpus policy/providers/budget/cache/milestone.
- `pytest-launcher-parent-v2.xml` : 53 PASS, 403,84 s, opt-in Linux réel activé, launcher adversarial, runtime Python, collecte, couverture Python et Node. Code produit exécuté exclusivement dans Docker NETNONE. La première commande parent avait un nom de fichier de test inexistant et n'a collecté aucun test ; elle n'est pas une preuve.

Ces résultats portent sur les mécanismes de la fabrique. Les fixtures synthétiques de cache ne sont pas des preuves de conformité de Relais Support. La globale et la campagne REM-25 ne sont pas déclarées réussies ici.

Complément : le reçu `final-admission.json` désigne maintenant l'admission actuelle et commence NOT_VERIFIED à chaque tentative. Son prédécesseur est conservé sous un nom `final-admission-prior-<uuid>.json`. Un échec d'attestation actuelle ne laisse donc ni fichier courant PASS ni télémétrie prématurée PASS. Les rapports et preuves X/R/V historiques ne sont pas modifiés. `current-admission-policy-parent-v2.xml` : 95 PASS, 5,23 s, incluant les deux nouveaux contrôles du reçu et les contre-tests indépendants des personas inconnues avec/sans préchauffage, désormais inchangés et verts. La v1 avait un nom de fichier de test inexistant et zéro collecte ; aucune preuve n'en est tirée.
