# Image embarquée et sorties capturées — 2026-10-12

Base intégrée f69145fb, branche codex/rem-execution.

`IsolatedValidator.run_captured(root,ecosystem,command,mode='runtime') -> (rc,stdout,stderr,environment)` conserve les flux distincts, sans export. Snapshot filtré, environnement Linux verrouillé, net-none; timeout nettoie le container possédé. Un diagnostic stderr ne devient jamais une aide CLI stdout par concaténation.

`RuntimeSession(...,mount_stage=False)` exige un ID local sha256 immuable et un WORKDIR /app vérifié. Aucun bind source n'est passé à Docker; /app vient de l'image embarquée. L'option reste identique au restart. Défaut mount_stage=True pour les validations source, toujours /app readonly.

Preuve réelle : `AUTOSPEC_REAL_LINUX_VALIDATION=1 pytest tests/test_captured_and_baked_validation.py -q` : **2 passed / 40.37s**. Deux flux séparés, timeout de commande isolée, build recette factory, image finale immutable, stage main.py divergent qui aurait levé mais non exécuté, HTTP retourne BAKED_SOURCE_ONLY, inspection sans Mounts et network none. Le tag UUID de la preuve seulement est retiré, sans prune ni force-remove d'un ID partagé.

Aucun code produit lancé sur l'hôte, aucun appel Claude/API payant. Le comportement métier et le déploiement/persistance complet restent à raccorder au harnais indépendant.
