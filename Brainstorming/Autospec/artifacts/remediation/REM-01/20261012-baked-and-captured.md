# Image embarquée et sorties capturées — 2026-10-12

Base intégrée f69145fb, branche codex/rem-execution.

`IsolatedValidator.run_captured(root,ecosystem,command,mode='runtime') -> (rc,stdout,stderr,environment)` conserve les flux distincts, sans export. Snapshot filtré, environnement Linux verrouillé, net-none; timeout nettoie le container possédé. Un diagnostic stderr ne devient jamais une aide CLI stdout par concaténation.

`RuntimeSession(...,mount_stage=False)` exige un ID local sha256 immuable et un WORKDIR /app vérifié. Aucun bind source n'est passé à Docker; /app vient de l'image embarquée. L'option reste identique au restart. Défaut mount_stage=True pour les validations source, toujours /app readonly.

Preuve réelle : `AUTOSPEC_REAL_LINUX_VALIDATION=1 pytest tests/test_captured_and_baked_validation.py -q` : **2 passed / 40.37s**. Deux flux séparés, timeout de commande isolée, build recette factory, image finale immutable, stage main.py divergent qui aurait levé mais non exécuté, HTTP retourne BAKED_SOURCE_ONLY, inspection sans Mounts et network none. Le tag UUID de la preuve seulement est retiré, sans prune ni force-remove d'un ID partagé.

Aucun code produit lancé sur l'hôte, aucun appel Claude/API payant. Le comportement métier et le déploiement/persistance complet restent à raccorder au harnais indépendant.

## Raccords inspect/detach/peer/couverture

RuntimeSession.inspect_configuration() inspecte à nouveau ID/owner/image et retourne uniquement user/read_only/cap_drop/privileged/security_opt/network_mode/published_ports/mounts/volume attestation; aucune variable d'environnement/secrets. detach() supprime le container exact en conservant volume et origin, attach() crée un nouvel ID sur ce même volume. close() final supprime seulement le volume éphémère de validation. Entrée/fermeture/attach sont sérialisées.

Le relais TCP utilise le peer IPv4 loopback reçu du kernel comme source_address dans Linux; tout peer non-loopback refusé, aucun XFF de confiance. Limite Windows réellement observée : bind source127.0.0.2 accepte mais connect vers127.0.0.1 expire10s; aucune configuration hôte modifiée. La preuve publique valide127.1 et XFF ignoré; un exec supervisor basePython-I dans Linux prouve un véritable peer kernel127.2 sur la même API standard. Une assertion de support public Windows multi-IP reste NON VERIFIABLE, pas simulée par XFF.

Preuve runtime étendue : AUTOSPEC_REAL_LINUX_VALIDATION=1 pytest tests/test_runtime_session.py : **16 passed / 122.69s**. IDs/volume inspectés entre detach et attach, SQLite conservée, Origin/refus403, sourceRO, timeoutexec cleanup, port étranger conservé, configuration hardening et peer réel Linux. Un échec initial de probe public127.2 a produit la limite ci-dessus, pas un PASS masqué.

Python coverage impose pytest -o addopts= et --cov-config=/dev/null. Un inventaire des fichiers source pré-exécution/hashés est requis intégralement dans le rapport. Les totaux sont recalculés seulement sur cet inventaire, excluent tests/fichiers étrangers et refusent comptes incohérents. autospec_inventory contient source/files/source_fingerprint/environment_fingerprint/image. Preuve réelle collection/couverture avec .coveragerc omit=business.py et addopts --no-cov/redirect report adverses : **2 passed,14 deselected / 55.22s**. Source omise rejetée; faux totaux étrangers ignorés. Rapports natifs restent soumis à l'intégrité/admission indépendante, jamais une preuve métier seuls.
