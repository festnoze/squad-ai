import json
from pathlib import Path
out = Path('CV/architecture-concept')
sections = [
('clients','Clients','Satellites d’entrée','Les satellites clients se séparent du sas.'),
('edge','Accès et sécurité','Enceinte extérieure','Les filtres et la passerelle se déploient.'),
('api','Tier 1 — Présentation / API','Plateau supérieur','La façade recule, les endpoints et filtres deviennent visibles.'),
('app','Tier 2 — Application','Plateau de coordination','Les cas d’usage se déploient et révèlent leurs ports.'),
('domain','Tier 3 — Domaine','Noyau central','Les enveloppes s’écartent autour du noyau métier.'),
('infra','Tier 4 — Infrastructure','Plateau inférieur et cartouches','Les adaptateurs se retirent de leur logement, sans modifier le noyau.'),
('external','Données et services connectés','Satellites de sortie','Les services s’éloignent, reliés par leurs connecteurs.'),
('delivery','CI/CD et orchestration','Rail de fabrication et socle','Un artefact parcourt le rail et rejoint les réplicas et workers.'),
('ops','Observabilité','Couronne de capteurs','Les capteurs se détachent et révèlent les signaux d’exploitation.')]
group_rows = [
('clients','interfaces','Interfaces','web:Frontend web;mobile:Client mobile;admin:Back-office'),
('edge','protection','Protection','cdn:DNS / CDN;waf:WAF / TLS;proxy:Reverse proxy'),
('edge','routing','Routage','gateway:API Gateway;limits:Quotas / rate limit;balance:Load balancer'),
('api','endpoints','Endpoints','router:Routeur / versioning;controller:Contrôleurs REST;pagination:Pagination / filtres'),
('api','contracts','Façade et contrats','facade:Façade API;dto:DTO entrée / sortie;api_mapper:Mapping des DTO'),
('api','guards','Filtres d’entrée','auth:Auth / autorisations;validation:Validation des entrées;errors:Gestion des erreurs;correlation:Contexte de requête'),
('app','usecases','Cas d’usage','create:Créer une ressource;read:Lire une ressource;workflow:Orchestrer un workflow'),
('app','coordination','Coordination','command_bus:Bus de commandes;query_bus:Bus de requêtes;uow_port:Port transaction;schedule:Tâches planifiées'),
('app','ports','Ports / interfaces','repo_port:Port repository;read_port:Port de lecture;event_port:Port d’événements;external_port:Ports externes'),
('domain','models','Modèles métier','aggregate:Agrégats;entity:Entités;value:Objets valeur;factory:Fabriques métier'),
('domain','rules','Règles métier','policy:Politiques métier;invariants:Invariants;domain_service:Services de domaine'),
('domain','events','Événements métier','domain_event:Événements de domaine;event_payload:Contrats d’événements'),
('infra','persistence','Persistance','repository:Repositories concrets;orm:ORM / modèles de table;db_mapper:Mapping métier / table;transaction:Unité de travail;driver:Pilote de base;migrations:Migrations'),
('infra','integrations','Intégrations','http:Adaptateurs HTTP;resilience:Timeout / retry / circuit breaker;serialization:Sérialisation;search_adapter:Adaptateur recherche;blob_adapter:Adaptateur fichiers'),
('infra','messaging','Asynchronisme','outbox:Outbox transactionnelle;relay:Relais outbox;consumer:Consommateurs / workers;idempotency:Idempotence / dédoublon'),
('infra','technical','Services techniques','cache_adapter:Adaptateur cache;config:Configuration;secrets:Accès aux secrets;health:Health / readiness'),
('external','data','Stockage','database:Base relationnelle;cache:Cache partagé;search:Moteur de recherche;blob:Stockage de fichiers'),
('external','queues','Messagerie','broker:Broker / files;dlq:File de rejet (DLQ)'),
('external','partners','Services externes','idp:Identité OIDC;payment:Paiement;email:E-mail / notification'),
('delivery','buildchain','Construire','git:Git / revue de code;quality:Lint / tests / sécurité;build:Build / image / SBOM'),
('delivery','release','Livrer','registry:Registre d’artefacts;staging:Staging / vérifications;rollout:Déploiement progressif'),
('delivery','platform','Orchestrer','iac:Infrastructure as Code;cluster:Orchestrateur de conteneurs;replicas:Réplicas API;workers:Workers / jobs;vault:Coffre de secrets'),
('ops','collect','Collecter','instrument:Instrumentation;collector:Collecteur de télémétrie'),
('ops','signals','Observer','traces:Traces distribuées;metrics:Métriques;logs:Journaux'),
('ops','react','Réagir','dashboard:Tableaux de bord;alerts:Alertes / SLO')]
groups=[]; nodes=[]
for section,gid,label,raw in group_rows:
    ids=[]
    for item in raw.split(';'):
        nid,nlabel=item.split(':',1)
        nodes.append(dict(id=nid,label=nlabel,group=gid,section=section))
        ids.append(nid)
    groups.append(dict(id=gid,label=label,section=section,nodes=ids))
lookup={n['id']:n for n in nodes}
flows=[]
def flow(fid,label,kind,chains,extra=()):
    edges=[]
    for chain in chains:
        path=chain.split('>')
        edges.extend(dict(source=a,target=b) for a,b in zip(path,path[1:]))
    edges.extend(dict(source=a,target=b,label=l) for a,b,l in extra)
    flows.append(dict(id=fid,label=label,kind=kind,edges=edges))
flow('command','Création d’une ressource','execution',[
'web>cdn>waf>proxy>gateway>limits>balance>router>auth>validation>controller>dto>api_mapper>facade>command_bus>create>aggregate>policy>invariants',
'create>repo_port>repository>db_mapper>orm>driver>database','create>uow_port>transaction>orm'],[('auth','idp','Clés OIDC')])
flow('query','Lecture d’une ressource','execution',[
'web>cdn>waf>proxy>gateway>limits>balance>router>auth>controller>pagination>facade>query_bus>read>read_port',
'read_port>cache_adapter>cache','read_port>repository>orm>driver>database','read>dto>controller'])
flow('event','Événement asynchrone','event',[
'create>aggregate>domain_event>event_payload','create>event_port>outbox>database>relay>broker>consumer>idempotency>workflow>external_port>http>resilience>email'],[('consumer','dlq','Après échecs'),('outbox','database','Même transaction que la modification métier')])
flow('delivery','Livraison d’une version','delivery',[
'git>quality>build>registry>staging>rollout>cluster>replicas>router','cluster>workers>consumer','iac>cluster','vault>secrets','config>replicas','migrations>database'])
flow('telemetry','Télémétrie et alerte','telemetry',[
'correlation>instrument>collector','controller>instrument','workflow>instrument','repository>instrument','consumer>instrument',
'collector>traces>dashboard','collector>metrics>dashboard','collector>logs>dashboard','metrics>alerts','health>cluster'])
flow('connections','Connexions complémentaires','execution',[
'http>serialization>payment','search_adapter>search','blob_adapter>blob','secrets>vault',
'domain_service>policy','factory>aggregate','aggregate>entity>value','schedule>workflow'])
dependencies=[
('controller','facade','appelle'),('facade','create','appelle'),('create','aggregate','utilise le domaine'),
('create','repo_port','dépend du contrat'),('create','uow_port','dépend du contrat'),('read','read_port','dépend du contrat'),
('workflow','external_port','dépend du contrat'),('repository','repo_port','implémente'),('repository','read_port','implémente'),
('transaction','uow_port','implémente'),('http','external_port','implémente'),('outbox','event_port','implémente'),
('cache_adapter','read_port','implémente'),('repository','aggregate','reconstitue le modèle')]
model=dict(title='Architecture agnostique — concept pour un asset 3D',version=1,
assumptions=['Architecture illustrative : elle ne décrit pas une réalisation attestée du CV.',
'API Gateway et reverse proxy retenus pour AG / proxy.',
'Quatre couches logiques du backend ; les couches ne représentent pas nécessairement quatre déploiements.',
'Les flux d’exécution, événements, déploiement et télémétrie sont distincts des dépendances de code.',
'Les réponses synchrones reprennent le chemin inverse, omis dans la vue d’ensemble.',
'Les noms restent indépendants des fournisseurs et frameworks.'],
sections=[dict(id=s,label=l,visual_form=f,scroll_motion=m) for s,l,f,m in sections],groups=groups,nodes=nodes,flows=flows,
dependencies=[dict(source=a,target=b,label=l) for a,b,l in dependencies],
scroll=[dict(step=0,focus='all',label='Objet assemblé')]+[dict(step=i+1,focus=('entry' if s=='clients' else s),label=l,motion=m) for i,(s,l,f,m) in enumerate([s for s in sections if s[0]!='edge'])])
for f in flows:
    for e in f['edges']:
        if e['source'] not in lookup or e['target'] not in lookup: raise ValueError(e)
for e in model['dependencies']:
    if e['source'] not in lookup or e['target'] not in lookup: raise ValueError(e)
if len(lookup)!=len(nodes): raise ValueError('Duplicate node ID')
(out/'architecture.json').write_text(json.dumps(model,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def quote(s): return s.replace('"','&quot;')
lines=['flowchart TB','%% Architecture illustrative, flux d’exécution et dépendances de code distincts.']
for section,slabel,form,motion in sections:
    lines.append(f'  subgraph section_{section}["{quote(slabel)}"]')
    lines.append('    direction LR')
    for g in groups:
        if g['section']!=section: continue
        lines.append(f'    subgraph group_{g["id"]}["{quote(g["label"])}"]')
        for nid in g['nodes']: lines.append(f'      {nid}["{quote(lookup[nid]["label"])}"]')
        lines.append('    end')
    lines.append('  end')
seen=set()
for f in flows:
    lines.append(f'  %% {f["label"]}')
    for e in f['edges']:
        key=(e['source'],e['target'])
        if key in seen: continue
        seen.add(key)
        l=e.get('label',f['kind'])
        lines.append(f'  {e["source"]} -->|"{quote(l)}"| {e["target"]}')
lines.append('  %% Pointillés : dépendance de code, orientée vers le contrat.')
for a,b,l in dependencies: lines.append(f'  {a} -. "{quote(l)}" .-> {b}')
(out/'architecture-detail.mmd').write_text('\n'.join(lines)+'\n',encoding='utf-8')
summary='''flowchart TB
  subgraph CLIENTS["SATELLITES — CLIENTS"]
    UI["Frontend web · Mobile · Back-office"]
  end
  subgraph EDGE["ENCEINTE — ACCÈS"]
    PROXY["CDN · WAF · TLS<br/>Reverse proxy"]
    GW["API Gateway<br/>Quotas · Load balancer"]
  end
  subgraph BACKEND["BACKEND — QUATRE TIERS LOGIQUES"]
    subgraph API["01 · PRÉSENTATION / API"]
      CTRL["Contrôleurs · Routeur<br/>Versioning · Pagination"]
      DTO["Façade · DTO<br/>Mapping entrée / sortie"]
      GUARDS["Auth · Validation<br/>Erreurs · Contexte"]
    end
    subgraph APP["02 · APPLICATION"]
      UC["Cas d’usage<br/>Commandes · Lectures"]
      ORCH["Orchestration métier<br/>Bus · Tâches planifiées"]
      PORTS["Ports / interfaces<br/>Repository · Lecture<br/>Transaction · Événements · Externe"]
    end
    subgraph DOMAIN["03 · DOMAINE"]
      MODEL["Agrégats · Entités<br/>Objets valeur · Fabriques"]
      RULES["Services de domaine<br/>Politiques · Invariants"]
      EVT["Événements de domaine<br/>Contrats"]
    end
    subgraph INFRA["04 · INFRASTRUCTURE"]
      DATA["Repositories · Mapping<br/>ORM · Transactions<br/>Pilotes · Migrations"]
      ADAPT["Adaptateurs HTTP / cache<br/>Recherche · Fichiers<br/>Timeout · Retry · Circuit breaker"]
      ASYNC["Outbox · Relais<br/>Consumers · Workers<br/>Idempotence"]
    end
  end
  subgraph SERVICES["SATELLITES — DONNÉES ET SERVICES"]
    STORE[("BDD · Cache<br/>Recherche · Fichiers")]
    BROKER["Broker · Files<br/>File de rejet"]
    EXT["Identité OIDC<br/>Paiement · Notifications"]
  end
  subgraph DELIVERY["RAIL — CI/CD ET SOCLE D’ORCHESTRATION"]
    GIT["Git · Revue"]
    CI["Lint · Tests · Sécurité<br/>Build · Image · SBOM"]
    CD["Registry · Staging<br/>Déploiement progressif"]
    RUNTIME["Orchestrateur<br/>Réplicas API · Workers · Jobs"]
    CONFIG["IaC · Configuration<br/>Coffre de secrets"]
  end
  subgraph OPS["COURONNE — OBSERVABILITÉ"]
    OTEL["Instrumentation<br/>Collecteur"]
    SIGNALS["Traces · Métriques · Logs<br/>Tableaux de bord · Alertes"]
  end
  UI -->|HTTPS| PROXY --> GW --> GUARDS --> CTRL --> DTO
  GUARDS -->|OIDC| EXT
  DTO --> UC
  UC --> ORCH
  UC --> MODEL --> RULES
  MODEL --> EVT
  UC --> PORTS
  ORCH --> PORTS
  PORTS -->|exécution via les ports| DATA
  PORTS --> ADAPT
  PORTS --> ASYNC
  DATA -->|lecture / écriture| STORE
  ADAPT --> STORE
  ADAPT --> EXT
  EVT -->|événements recueillis par le cas d’usage| UC
  ASYNC -->|outbox transactionnelle| STORE
  ASYNC -->|publication / consommation| BROKER
  ASYNC -->|traitement asynchrone| ORCH
  DATA -. implémente .-> PORTS
  ADAPT -. implémente .-> PORTS
  GIT --> CI --> CD --> RUNTIME
  CONFIG --> RUNTIME
  RUNTIME -->|héberge| CTRL
  RUNTIME -->|héberge| ASYNC
  CONFIG -->|configure| ADAPT
  CTRL -->|télémétrie| OTEL
  UC -->|télémétrie| OTEL
  DATA -->|télémétrie| OTEL
  RUNTIME -->|télémétrie| OTEL
  OTEL --> SIGNALS
'''
(out/'architecture-overview.mmd').write_text(summary,encoding='utf-8')
print(json.dumps({'nodes':len(nodes),'groups':len(groups),'unique_flows':len(seen),'dependencies':len(dependencies),'outputs':[p.name for p in out.iterdir()]},ensure_ascii=False))

