# Reçus natifs de build et cache — 2026-10-12

`build_delivery_image(root,image,docker=...,timeout=...,evidence_root=external,snapshot_hash=source_snapshot(root).digest)` reste compatible avec `(ok,output)` et écrit `external/delivery-build.json`. Les deux options sont inséparables. Le store doit être extérieur/non aliasé; l'identité source est vérifiée avant et après build. Sans options, le contrat historique est conservé.

Payload : `version,status PASS|FAIL,snapshot_hash,image_id sha256|null,image_tag,isolated,no_host_dependencies,manifest_only_install,locks_sha256,frontend_files,commands`. Les hashes des locks et du dist réellement construit sont exacts. L'image finale reçoit un label factory autospec.snapshot, puis son ID/label sont inspectés. Le tag d'environnement de dépendances est aussi comparé à l'ID attesté avant le FROM : drift/tag remplaçé ou label source différent => FAIL, jamais un reçu vert.

`commands` contient :

- backend_install/frontend_install : argv uv/npm provenant de la recette factory recalculée/hashée, **rc=null**, execution attested-cache ou attested-layer. Les installs ne reçoivent pas un faux code0 : BuildKit peut réutiliser leurs couches. L'attestation complète lie manifest/lock/toolchain digest/platform/mode/version/recipe/image.
- builder associé : `prepare(...,receipt=dict)` rapporte cache_attested avec argv/rc null, ou build_attested avec le vrai argv/code Docker build observé et un output_tail borné. Un build frais de l'image n'affirme pas que chaque RUN a été réexécuté.
- typecheck_frontend_build : components=[typecheck,frontend_build], argv enveloppe Linux exacte, rc composé réellement obtenu. tsc -b && Vite partage un code de sortie; aucun rc individuel inventé. Sans tsconfig, seul frontend_build est enregistré.
- image_build : vrai argv/code de sortie Docker build, network=none et recette factory hashée. Aucun Dockerfile produit n'est exécuté.

Failure frontend conserve son rc non nul et ne publie ni dist vert ni image_build supposé. Exceptions/timeout/drift laissent un reçu FAIL avec l'étape réellement observée. Une erreur d'écriture du reçu remonte, sans admission silencieuse. Les gates OPS doivent distinguer cache attesté d'installation exécutée, puis vérifier le snapshot/image exact; un JSON non vide n'est pas une preuve suffisante.

Tests dédiés : `AUTOSPEC_REAL_LINUX_VALIDATION=1 pytest tests/test_delivery_build_receipts.py -q` : **7 PASS / 39.20s**. Builder initial + cache vérifié, recette/manifests seuls, rc null pour installs cache, composite tsc/Vite, refus drift image/tag, refus evidence dans produit/snapshot incorrect, échec frontend conservé. Preuve réelle : locks Linux Python/Node, frontend TypeScript/Vite, deux images finales Docker inspectées avec label snapshot exact, seconde dépendance cache attestée, aucun .venv/node_modules hôte, source inchangée. Seuls les deux tags UUID de test sont retirés, sans prune/force-remove.

Limites : aucun appel modèle payant, aucune qualification globale OPS avant raccord du coordinateur/pipeline. Les hooks Git hôte relevés séparément par contre-revue restent du périmètre parent; aucun probe hostile n'a été lancé sur l'hôte pour les « démontrer ».
