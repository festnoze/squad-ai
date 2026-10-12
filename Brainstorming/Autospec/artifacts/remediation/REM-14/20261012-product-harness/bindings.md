# Raccord automatique des faits techniques revus

Le produit ne définit pas l'oracle. Les valeurs attendues viennent du brief/référentiel immuables. Le reviewer travaille hors produit, sans exécuter ses scripts sur l'hôte. Le choix utilisateur est la revue par sous-agents GPT6.1 à partir de paquets locaux ; aucun export de sources vers Claude ni appel Claude n'est effectué. Ces API ne déclenchent aucun appel LLM.

## Cycle et chemins exacts

1. Geler les sources avec `source_snapshot`/`freeze_snapshot` et charger le contrat superviseur.
2. Donner au reviewer le brief, référentiel et les fichiers source lisibles (texte seulement). Demander uniquement la correspondance factuelle tables/colonnes, commandes, routes, symboles et sélecteurs selon `binding_proposal_schema()`. Ne jamais demander de changer les attentes pour satisfaire le code.
3. Appeler `await prepare_binding_proposal(candidate, fixtures, contract=contract, snapshot_root=frozen, snapshot_hash=digest)`. Cette fonction vérifie la structure, l'identité réelle du snapshot et les SHA des fichiers cités. Elle ne publie pas et n'accorde aucun PASS.
4. Revue indépendante des octets exacts et des entrées de fixtures, incluant les variantes de concurrence/filtres. Deux artefacts R externes doivent approuver explicitement les tags retournés `binding_checks` et `fixture_checks`, avec leurs hashes. Un verdict `NOT_VERIFIED` ou `FAIL` n'est pas converti en approbation.
5. Construire deux `Proof('R', path, sha256, snapshot_hash, contract_hash, checks=..., passed=True)` uniquement après cette revue ; appeler `await install_reviewed_configuration(proposal, binding_review=..., fixture_review=..., supervisor_root=supervisor, snapshot_root=frozen)`.
6. Le pipeline appelle directement `verify_vertical(state, contract, frozen, digest, supervisor)` puis `verify_project(...)`. Même signature positionnelle/kwargs.

Fichiers de contrôle stables : `supervisor/product-bindings.json` et `supervisor/reviewed-fixtures.json`. La paire porte `fixture_fingerprint` ; une publication interrompue/mélangée est refusée. Toute modification du contrat/snapshot/mapping/fixtures/source/revue invalide les attestations concernées. La préparation ne modifie aucun contrat ni fichier produit.

Sorties du jalon : `supervisor/vertical/<snapshot>/evidence`. Sorties packs : `supervisor/reports/<snapshot>/harness`. Preuves externes : `supervisor/proofs.json` et `supervisor/observations.json`. Le produit ne reçoit aucun de ces chemins en montage.

## Proposition minimale exacte, illustrée sur notre métaproduct Linux

L'exemple est une fixture de validation indépendante, **pas** la configuration du benchmark historique. Les noms doivent être constatés dans les sources du candidat avant revue.

```json
{
  "source_files": ["main.py", "pyproject.toml", "uv.lock"],
  "bindings": {
    "database_path": "/var/lib/autospec-validation/support.sqlite",
    "tables": {
      "users": {"name":"users","columns":{"id":"id","email":"email","email_normalized":"email_normalized","password_hash":"password_hash","role":"role","active":"active"}},
      "tickets": {"name":"tickets","columns":{"id":"id","owner_id":"owner_id","title":"title","description":"description","status":"status","priority":"priority","assignee_id":"assignee_id","version":"version","created_at":"created_at","updated_at":"updated_at"}},
      "messages": {"name":"messages","columns":{"id":"id","ticket_id":"ticket_id","author_id":"author_id","content":"content","visibility":"visibility","created_at":"created_at"}},
      "ticket_events": {"name":"ticket_events","columns":{"id":"id","ticket_id":"ticket_id","event_type":"event_type","created_at":"created_at"}},
      "idempotency_keys": {"name":"idempotency_keys","columns":{"actor_id":"actor_id","kind":"kind","client_request_id":"client_request_id","result_id":"result_id"}},
      "sessions": {"name":"sessions","columns":{"token_hash":"token_hash","user_id":"user_id","csrf":"csrf","expires_at":"expires_at"}}
    },
    "commands": {
      "migrate_fresh":{"argv":["/opt/venv/bin/python","main.py","migrate_fresh"],"parameters":["fault"],"timeout":30},
      "bootstrap":{"argv":["/opt/venv/bin/python","main.py","bootstrap"],"parameters":["credentials"],"timeout":30},
      "seed":{"argv":["/opt/venv/bin/python","main.py","seed"],"parameters":["payload"],"timeout":30}
    },
    "runtime_command":["/opt/venv/bin/python","main.py"],
    "auth_path":"/api/auth/login","csrf_field":"csrf_token","ticket_path":"/api/tickets/{id}",
    "auth_required":true,"internal_port":8000,"local_cookie_mode":true,
    "instrumentation":{"app_module":"main","app_attribute":"app","clock_module":"main","clock_attribute":"now","clock_kind":"epoch","password_module":"","password_attribute":"","business_tables":["tickets","messages"],"audit_table":"ticket_events","races":{"ticket_patch":[["PATCH","/api/tickets/[a-f0-9-]+"]]},"race_winners":{},"proxy_headers":false},
    "query_plans":{"tickets":["SELECT * FROM tickets WHERE owner_id=?",["owner"]]},
    "browser_bindings":{"email":"#email","password":"#password","login":"#login","ticket_list":"#tickets","create":"#create","title":"#title","description":"#description","submit":"#submit","detail":"#detail"},
    "browser_routes":{"home":"/","ticket":"/tickets/{id}","admin":"/admin"}
  }
}
```

Le candidat ne fournit pas `review`, `snapshot_hash`, `contract_hash`, `source_files` SHA ou `fixture_fingerprint` dans `bindings` : le superviseur calcule/attache ces champs. Toutes les clés indiquées sont explicites, `instrumentation:null` est permis pour une tranche sans diagnostic. Absence de symboles clock/dummy/race = ports concernés indisponibles, jamais succès par défaut. Le symbole `password_*` doit être le **vérificateur de hash factice**, pas une fonction quelconque.

## Entrées de fixtures (pas attendus tirés des réponses)

```json
{"cases":{"VERTICAL":{
  "accounts":{
    "alice":{"id":"$uuid","email":"alice@example.test","password":"$generated","role":"client","active":true},
    "emma":{"id":"$uuid","email":"emma@example.test","password":"$generated","role":"admin","active":true}
  },
  "aliases":{"admin":"emma"},
  "tickets":{},
  "metadata":{"provisioning":["migrate_fresh","bootstrap","seed"],"bootstrap_actor":"emma","vertical_actor":"alice"},
  "commands":{
    "migrate_fresh":{},
    "bootstrap":{"credentials":{"$ref":"accounts.emma"}},
    "seed":{"payload":{"accounts":{"$ref":"accounts"},"tickets":[]}}
  }
}}}
```

Les mots de passe sont générés avant toute commande, transmis uniquement par JSON stdin et jamais conservés dans les preuves. UUID générés : tranche verticale uniquement ; campagne complète : UUID/dates fixes indépendants, cinq acteurs exacts et douze tickets répartis selon le brief, conversations publiques/internes. `tests.test_product_harness.fixture_definition()` fournit la métadéfinition exacte à cinq comptes/douze tickets utilisée pour nos tests ; elle est volontairement minimale et **n'est pas** le dataset complet des 57 exigences.

Chaque RID et chaque E2E utilisé doit avoir une entrée `cases` explicite ; pas de seed nominal par défaut pour un cas inconnu. Une variante est `{"options":{"query_count":50},"fixture":{"accounts":...,"tickets":...,"metadata":...,"commands":...}}` dans `variants`. La correspondance `options` est exacte et unique. Variantes nécessaires selon packs : `query_count=1/50`, `migration_scenario=true`, `assignment_scenario=...`, `mixed_conversation=...` ; reprendre les appels exacts des packs, ne pas inventer une définition approximative.

Les ports d'administration du harness ne deviennent jamais des routes debug livrées. Une CLI produit non JSON peut être liée à un pont `python -c` **revue explicite**, convertissant JSON stdin vers sa saisie/argv dans le conteneur ; aucun import produit/shell/script/configuration produit sur l'hôte. Un mécanisme absent reste indisponible.

## Rendez-vous / fautes / horloge

`races` lie le point utilisé par le pack à des paires `[METHOD, regex de chemin fullmatch]`. `race_winners` lie un nom de gagnant à l'une de ces routes exactes. Le launcher de confiance attend avant d'entrer dans le produit et avant BEGIN ; deux connexions réelles sont enregistrées. Une ordonnance fermeture/message doit désigner **deux routes distinctes** et les deux gagnants. Deux routes identiques ne peuvent pas déterminer quel gagnant nommé a gagné.

Horloge : symbole source exact et type de retour explicite `epoch` ou `utc_datetime`, figé à la valeur initiale puis avancé par le superviseur. `proxy_headers` doit reproduire le mode du serveur constaté dans les sources ; il n'est jamais durci pour obtenir un PASS. Les IP alternatives sont des sockets Linux dont l'adresse source est réellement donnée au noyau, pas des en-têtes X-Forwarded-For ; les IP publiques alternatives Windows restent non vérifiées. Faute `after_business_before_audit` : tables métier/audit exactes, erreur SQLite injectée après une écriture métier avant INSERT audit. Cette session diagnostique est distincte du runtime final non instrumenté ; ce n'est pas une protection contre un produit hostile inspectant son interpréteur.

## Reçus externes et OPS

`observations.json` : `{snapshot_hash,contract_hash,observations:{name:ProofX|[ProofX...]}}`. Une liste permet plusieurs paramètres exacts (notamment les deux scopes `secret_scan`). Deux reçus pour les mêmes paramètres sont refusés comme ambigus. Le fichier du Proof est `{name,parameters:{},value:...,snapshot_hash,contract_hash}` avec tag `OBS:<name>`. `passed=True` signifie **observation obtenue**, pas produit conforme. Un `value` négatif demeure négatif. `proofs.json` : `{snapshot_hash,contract_hash,proofs:{RID:[Proof...]}}` ; tags `RID` ou `RID:sous-probe`, mêmes hashes et artefacts sous superviseur.

Pour les runners de confiance : `await SupervisorEvidenceStore(supervisor, snapshot, contract).record_native_observation(name, value, parameters={...}, source_proofs=[ProofXouV...])`. Les artefacts natifs doivent déjà exister dans la racine superviseur avec SHA/identités intacts ; absence => indisponible. La publication conserve les valeurs négatives et ne délivre aucune R. `publish_native_proof(RID, ProofXouV)` ajoute un reçu natif existant à l'index sans toucher aux R.

- `delivery_build` : `image_id=sha256:...`, `isolated/no_host_dependencies/manifest_only_install=true`, `locks` SHA exacts, `commands=[{kind,argv,return_code}]`. Kinds requis : backend_install/image_build et, avec frontend, frontend_install/typecheck/frontend_build. `frontend_files` SHA des assets indépendamment construits autorisés uniquement sous frontend/dist. Le runtime vérifie ensuite chaque octet réellement baked sans montage /app.
- `browser_e2e` : coordinator exécute réellement six appels individuels `alone`, puis les six `together`, avec reset explicite par scénario et X/V natifs. Pour OPS-03 il lance E2E-01/02 dans le runtime baked, avec `image_id` exact, et publie les observations sous `parameters={image_id:...}` afin de préserver séparément les douze runs source. Absence de fixture/port/sélecteur => NOT_VERIFIED ; une exécution source-montée n'est pas renommée image finale.
- `docs_audit` : README path/SHA ; documented_commands argv/rc réellement exécutés ; configuration path/source_sha256/secrets_found ; fixtures_explicit et accounts_before_fixture observé ; audit AVAILABLE/date timezone/tool/return_code/report_valid/findings/artifacts ProofX `OBS:audit_raw`. Chaque finding comporte severity/exploitable/arbitration. High/critical exploitable non arbitré => FAIL ; audit absent => NOT_VERIFIED. R séparé couvre README/configuration/audit.
- `execution_timings` : machine `{os,cpu,python,docker}`, seconds `{install,tests,browser,build,docker}` réels. Coût LLM seulement rapporté ; cibles durées diagnostiques.

OPS-02 utilise l'inspection effective du conteneur possédé et R sur exclusions/installers. OPS-04 crée vraiment ticket/réponse/note, compare toutes les lignes après restart puis detach/attach du même volume, rejoue les mêmes trois clés et exige les mêmes IDs/HTTP200 sans écriture. Fermeture du contexte nettoie uniquement conteneur/volume de validation possédés.

Port `sqlite_quality_probe(state, contract, snapshot_root, snapshot_hash, supervisor)` pour `NativeQualityCollector` : contexte Linux diagnostique distinct, case `TST-04` et `metadata.quality_actor` explicites, transactions HTTP réelles, IDs de connexions app réellement instrumentées, export SQLite exact, vrai restart avec comparaison DB/API, puis fermeture du contexte et absence du conteneur/volume exacts avant d'attester `cleanup_owned_only`. Le callback du collecteur se raccorde par closure `(adapter, snapshot, contract_hash)` sur ces cinq paramètres. L'export demeure privé superviseur et n'est pas livré au produit ni inclus dans ce bundle de preuves. La revue des fixtures de chaque suite native reste séparément obligatoire.

Les observations native suites/coverage et l'audit doivent être émises par leurs runners indépendants : aucune synthèse à partir d'une narration du produit. Les preuves R ne sont jamais générées par le contenu de notre fixture ni par le vérificateur runtime.
