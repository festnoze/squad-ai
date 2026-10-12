import json, runpy
from pathlib import Path
base=Path(__file__).resolve().parent
runpy.run_path(str(base/'build_classic_concept.py'))
p=base/'architecture.json'
m=json.loads(p.read_text(encoding='utf-8'))
m['version']=2
m['title']='Architecture API classique + workflow agentique'
m['assumptions'] += ['Tous les services externes à l’API sont représentés dans le périmètre infrastructure, avec distinction adaptateur interne / service distant.', 'Le workflow applicatif décrit les agents et les transitions ; un adaptateur LangGraph peut exécuter cette définition.', 'Skills = instructions et procédures ; tools = opérations exécutables derrière des ports.', 'Les agents échangent des messages via l’état du graphe / des handoffs explicites.', 'La relecture en ligne et les évaluations LLM hors du chemin de réponse sont deux mécanismes distincts.', 'Cache de réponse LLM, cache de prompts et checkpoints de workflow sont trois stockages distincts.']
# External dependencies and operations now belong to the infrastructure layer.
for n in m['nodes']:
    if n['section'] in ['external','ops']: n['section']='infra'
for g in m['groups']:
    if g['section'] in ['external','ops']:g['section']='infra'
    g['scope']='remote' if g['id'] in ['data','queues','partners','signals','react'] else 'internal'
    g['focus']='services' if g['id'] in ['data','queues','partners'] else 'ops' if g['id'] in ['collect','signals','react'] else g['section']
m['sections']=[s for s in m['sections'] if s['id'] not in ['external','ops']]
for s in m['sections']:
    if s['id']=='app':s.update(label='Tier 2 — Application et agents',visual_form='Plateau de coordination et arène d’agents',scroll_motion='Le plateau s’ouvre en pétales et expose les agents, les conditions et les connecteurs.')
    if s['id']=='infra':s.update(label='Tier 4 — Infrastructure : adaptateurs et services externes',visual_form='Socle technique et cartouches de services',scroll_motion='Les adaptateurs coulissent ; les cartouches LLM, cache, Langfuse et données se séparent à l’intérieur du socle.')

def group(section,gid,label,focus,raw,scope='internal'):
    ids=[]
    for item in raw.split(';'):
        nid,nlabel=item.split(':',1)
        m['nodes'].append(dict(id=nid,label=nlabel,group=gid,section=section))
        ids.append(nid)
    m['groups'].append(dict(id=gid,label=label,section=section,nodes=ids,focus=focus,scope=scope))
group('app','agent_graph','Workflow agentique','agentic','agent_run:Service de workflow;graph_state:État partagé / messages;supervisor:Agent superviseur;route_decision:Quel agent appeler ?;research_agent:Agent recherche;analyst_agent:Agent analyse;writer_agent:Agent synthèse;review_agent:Agent relecteur;quality_gate:Révision nécessaire ?;run_output:Résultat structuré;run_failed:Arrêt contrôlé;run_budget:Budget / nombre d’itérations')
group('app','agent_capabilities','Anatomie d’un agent','agent','agent_profile:Rôle / objectifs / contexte;skills:Catalogue de skills;skill_loader:Chargement des instructions;tool_decision:Outil nécessaire ?;tool_catalog:Tools disponibles;tool_dispatch:Exécuteur de tools;agent_messages:Messages / handoffs;agent_response:Réponse modèle structurée')
group('app','ai_ports','Ports IA / mémoire','agent','llm_port:Port génération LLM;prompt_port:Port de prompts;tool_port:Port d’exécution tools;memory_port:Port mémoire / retrieval;checkpoint_port:Port checkpoint;trace_port:Port de traçage;graph_port:Port d’orchestration')
group('infra','ai_adapters','Adaptateurs IA / tools','infra','llm_adapter:Adaptateur LLM;prompt_adapter:Adaptateur prompts;tool_adapter:Adaptateurs de tools;memory_adapter:Adaptateur retrieval;checkpoint_adapter:Checkpointer;langgraph_runtime:Exécuteur LangGraph;trace_adapter:Adaptateur traces Langfuse;llm_client:Client fournisseur LLM;prompt_render:Compilation du prompt')
group('infra','cache_layer','Couche de cache','cache','cache_key:Clé contexte / prompt / modèle;cache_lookup:Lecture cache de réponse;cache_decision:Cache hit ou miss ?;cache_write:Écriture / TTL;cached_output:Réponse LLM en cache;prompt_local_cache:Cache local des prompts;cache_invalidate:Invalidation / versions')
group('infra','llm_services','Services de modèles','llm','llm_provider:Service LLM distant;embedding_provider:Service embeddings;judge_provider:Service LLM évaluateur',scope='remote')
group('infra','memory_services','Mémoire et cache distants','cache','response_cache:Cache de réponses LLM;checkpoint_db:Stockage des checkpoints;vector_db:Base vectorielle',scope='remote')
group('infra','lf_prompts','Langfuse · prompts','langfuse','lf_prompts:Registre de prompts;prompt_version:Version / label du prompt;prompt_variables:Variables et schéma',scope='remote')
group('infra','lf_traces','Langfuse · traces','langfuse','lf_traces:Traces / sessions / spans;lf_generation:Générations / tokens / coût;lf_scores:Scores / annotations',scope='remote')
group('infra','lf_evals','Langfuse · évaluations','langfuse','lf_datasets:Datasets / références;lf_experiments:Expériences / régressions;lf_eval:Évaluateur LLM-as-judge;lf_code_eval:Évaluations déterministes;lf_feedback:Feedback humain',scope='remote')
group('infra','evaluation_jobs','Adaptateurs d’évaluation','langfuse','eval_job:Job d’évaluation asynchrone;eval_adapter:Adaptateur LLM évaluateur')
# Facade used by both conventional and agentic endpoints.
def add_flow(fid,label,kind,chains=(),extra=()):
    edges=[]
    for chain in chains:
        path=chain.split('>'); edges += [dict(source=a,target=b) for a,b in zip(path,path[1:])]
    edges += [dict(source=a,target=b,label=label) for a,b,label in extra]
    m['flows'].append(dict(id=fid,label=label,kind=kind,edges=edges))
add_flow('agentic','Workflow multi-agents','execution',[
'web>proxy>gateway>controller>facade>agent_run>graph_port>langgraph_runtime',
'agent_run>graph_state>supervisor>run_budget>route_decision',
'research_agent>analyst_agent>writer_agent>review_agent>quality_gate',
'research_agent>tool_decision>tool_dispatch>tool_port>tool_adapter>search',
'research_agent>agent_messages>graph_state', 'analyst_agent>agent_messages',
'graph_state>checkpoint_port>checkpoint_adapter>checkpoint_db',
'research_agent>llm_port>llm_adapter>llm_client>llm_provider'],[
('langgraph_runtime','supervisor','Exécute la définition applicative'),
('route_decision','research_agent','Si recherche nécessaire'),('route_decision','analyst_agent','Si analyse nécessaire'),('route_decision','writer_agent','Si contexte suffisant'),
('analyst_agent','research_agent','Demande de complément'),('tool_adapter','tool_dispatch','Résultat du tool'),('tool_dispatch','research_agent','Observation'),
('tool_decision','analyst_agent','Sans outil'),('quality_gate','writer_agent','À réviser et budget disponible'),('quality_gate','run_output','Validé'),('quality_gate','run_failed','Budget atteint / échec'),('run_output','dto','Réponse API')])
add_flow('agent','Skills, tools et échanges','execution',[
'research_agent>agent_profile>skills>skill_loader', 'research_agent>tool_decision>tool_catalog>tool_dispatch>tool_port>tool_adapter',
'research_agent>agent_messages>analyst_agent', 'research_agent>llm_port>llm_adapter',
'research_agent>memory_port>memory_adapter>vector_db', 'memory_adapter>embedding_provider'],[
('skill_loader','research_agent','Instructions chargées'),('tool_adapter','research_agent','Résultat de l’action'),('analyst_agent','agent_messages','Message de retour'),('agent_messages','graph_state','État partagé')])
llm_common='research_agent>llm_port>llm_adapter>prompt_port>prompt_adapter>prompt_local_cache>prompt_version>prompt_render>cache_key>cache_lookup>cache_decision'
add_flow('llm_miss','Appel LLM · cache miss','execution',[llm_common,'llm_client>llm_provider>agent_response>cache_write>response_cache','agent_response>research_agent'],[
('cache_lookup','response_cache','Lire'),('cache_decision','llm_client','Miss'),('cache_write','cached_output','Réponse versionnée'),('llm_adapter','trace_port','Trace de génération')])
add_flow('llm_hit','Appel LLM · cache hit','execution',[llm_common,'cached_output>agent_response>research_agent'],[
('cache_lookup','response_cache','Lire'),('cache_decision','cached_output','Hit : pas d’appel fournisseur'),('llm_adapter','trace_port','Trace du cache hit')])
add_flow('prompts','Prompt versionné','execution',[
'prompt_port>prompt_adapter>prompt_local_cache', 'lf_prompts>prompt_version>prompt_variables>prompt_render', 'prompt_version>cache_invalidate>cache_key'],[
('prompt_local_cache','lf_prompts','Actualisation / version absente'),('prompt_version','prompt_local_cache','Mettre en cache la version')])
add_flow('langfuse','Traces et évaluations','telemetry',[
'supervisor>trace_port>trace_adapter>lf_traces>lf_generation',
'research_agent>trace_port','tool_dispatch>trace_port',
'lf_traces>eval_job>eval_adapter>judge_provider>lf_scores', 'lf_feedback>lf_scores',
'lf_datasets>lf_experiments>lf_eval>judge_provider', 'lf_experiments>lf_code_eval>lf_scores'],[
('eval_job','lf_eval','Configuration de l’évaluateur'),('prompt_version','lf_generation','Lien à la version utilisée'),('lf_scores','quality','Régressions contrôlées en CI')])
add_flow('checkpoint','État et reprise de workflow','execution',[
'graph_state>checkpoint_port>checkpoint_adapter>checkpoint_db', 'memory_port>memory_adapter>vector_db'],[
('checkpoint_db','graph_state','Reprendre une exécution'),('graph_state','agent_messages','Messages conservés')])
for agent in ['supervisor','research_agent','analyst_agent','writer_agent','review_agent']:
    # Each agent shares the same capabilities through its own instance/configuration.
    next(f for f in m['flows'] if f['id']=='agent')['edges'] += [dict(source=agent,target='skills',label='Skills propres à cet agent'),dict(source=agent,target='tool_catalog',label='Tools autorisés'),dict(source=agent,target='llm_port',label='Génération'),dict(source=agent,target='agent_messages',label='Échange explicite')]
for a,b,l in [('agent_run','graph_port','dépend du contrat'),('langgraph_runtime','graph_port','implémente'),('research_agent','llm_port','dépend du contrat'),('llm_adapter','llm_port','implémente'),('prompt_adapter','prompt_port','implémente'),('tool_adapter','tool_port','implémente'),('checkpoint_adapter','checkpoint_port','implémente'),('trace_adapter','trace_port','implémente'),('memory_adapter','memory_port','implémente')]:m['dependencies'].append(dict(source=a,target=b,label=l))
# Label decisions explicitly for diagram / scene geometry.
for n in m['nodes']:
    n['shape']='decision' if n['id'] in ['route_decision','quality_gate','tool_decision','cache_decision'] else 'component'
m['sources']=[dict(title='Langfuse SDK prompt caching',url='https://langfuse.com/docs/prompt-management/features/caching'),dict(title='LangGraph workflows and agents',url='https://docs.langchain.com/oss/python/langgraph/workflows-agents'),dict(title='Langfuse prompt management',url='https://langfuse.com/docs/prompt-management/overview'),dict(title='Langfuse evaluation',url='https://langfuse.com/docs/evaluation/overview'),dict(title='Langfuse observability',url='https://langfuse.com/docs/observability/overview')]
m['views']=[
 dict(id='all',label='Vue d’ensemble',sections=[],groups=[]),
 dict(id='entry',label='Clients et accès',sections=['clients','edge'],groups=[]),
 dict(id='api',label='Façade API',sections=['api'],groups=[]),
 dict(id='app',label='Services applicatifs classiques',sections=[],groups=['usecases','coordination','ports']),
 dict(id='agentic',label='Workflow multi-agents',sections=[],groups=['agent_graph']),
 dict(id='agent',label='À l’intérieur d’un agent',sections=[],groups=['agent_capabilities','ai_ports']),
 dict(id='domain',label='Cœur métier',sections=['domain'],groups=[]),
 dict(id='infra',label='Infrastructure · adaptateurs',sections=[],groups=['persistence','integrations','messaging','technical','ai_adapters']),
 dict(id='llm',label='Infrastructure · appel LLM',sections=[],groups=['ai_adapters','cache_layer','llm_services','lf_prompts']),
 dict(id='cache',label='Infrastructure · caches et mémoire',sections=[],groups=['cache_layer','memory_services']),
 dict(id='langfuse',label='Infrastructure · Langfuse',sections=[],groups=['lf_prompts','lf_traces','lf_evals','evaluation_jobs','llm_services']),
 dict(id='services',label='Infrastructure · services externes',sections=[],groups=['data','queues','partners','llm_services','memory_services','lf_prompts','lf_traces','lf_evals','signals','react']),
 dict(id='ops',label='Infrastructure · observabilité',sections=[],groups=['collect','signals','react','lf_traces']),
 dict(id='delivery',label='CI/CD et orchestration',sections=['delivery'],groups=[])]
m['overview']=[
 dict(section='clients',items=[('o_clients','Interfaces web / mobile',['interfaces'])]),
 dict(section='edge',items=[('o_edge','Proxy / sécurité / gateway',['protection','routing'])]),
 dict(section='api',items=[('o_api','Façade / DTO / endpoints',['endpoints','contracts','guards'])]),
 dict(section='app',items=[('o_classic','Services API classiques',['usecases','coordination','ports']),('o_graph','Workflow multi-agents',['agent_graph']),('o_agent','Skills / tools / messages',['agent_capabilities']),('o_aiports','Ports IA / mémoire',['ai_ports'])]),
 dict(section='domain',items=[('o_domain','Modèles / règles / événements',['models','rules','events'])]),
 dict(section='infra',items=[('o_persistence','Persistance / événements',['persistence','messaging','data','queues']),('o_adapters','Adaptateurs / exécution',['integrations','technical','ai_adapters']),('o_models','LLM / embeddings / judge',['llm_services']),('o_cache','Caches / mémoire',['cache_layer','memory_services']),('o_lf','Langfuse : prompts / traces / évaluations',['lf_prompts','lf_traces','lf_evals','evaluation_jobs']),('o_ops','Observabilité générale',['collect','signals','react']),('o_partners','Services partenaires',['partners'])]),
 dict(section='delivery',items=[('o_delivery','CI/CD / régressions',['buildchain','release']),('o_runtime','Orchestration / IaC',['platform'])])]
m['scroll']=[dict(step=i,focus=v,label=l,motion=motion) for i,(v,l,motion) in enumerate([
('all','Machine assemblée','Silhouette compacte et flux discrets.'),('entry','Entrée','Le sas frontal s’ouvre.'),('api','Façade','Le capot expose les filtres et contrats.'),('app','Application','Les deux chemins classique et agentique se distinguent.'),('agentic','Arène d’agents','Le plateau se déploie en pétales ; les messages suivent une branche du graphe.'),('agent','Un agent','Un pod s’extrait ; ses skills, tools, contexte et ports se séparent.'),('domain','Noyau métier','Le noyau reste stable au centre.'),('llm','Services de modèles','Le socle ouvre ses adaptateurs et les cartouches LLM.'),('cache','Cache','Un embranchement hit / miss se révèle.'),('langfuse','Langfuse','Une cartouche se décompose en faces prompts, traces et évaluations.'),('delivery','Livraison','Le rail CI/CD se déroule jusqu’au socle de déploiement.'),('all','Réassemblage','Les pièces rejoignent leur logement et les flux restent attachés.')])]
ids={n['id'] for n in m['nodes']}
assert len(ids)==len(m['nodes'])
for f in m['flows']:
    for e in f['edges']:assert e['source'] in ids and e['target'] in ids,e
for g in m['groups']:assert set(g['nodes'])<=ids
assert all(n['section']=='infra' for n in m['nodes'] if n['id'] in ['llm_provider','response_cache','lf_prompts','lf_traces','lf_eval','metrics','logs'])
p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
lookup={n['id']:n for n in m['nodes']}
def q(s):return s.replace('"','&quot;')
def mermaid(subset=None):
    chosen=ids if subset is None else set(subset)
    lines=['flowchart TB','%% Architecture conceptuelle. Services distants regroupés dans le périmètre infrastructure.']
    for section in m['sections']:
        sg=[g for g in m['groups'] if g['section']==section['id'] and set(g['nodes'])&chosen]
        if not sg:continue
        lines += [f'  subgraph section_{section["id"]}["{q(section["label"])}"]','    direction LR']
        for g in sg:
            label=g['label']+(' · service externe' if g['scope']=='remote' else '')
            lines.append(f'    subgraph group_{g["id"]}["{q(label)}"]')
            for nid in g['nodes']:
                if nid not in chosen:continue
                n=lookup[nid]; a,b=('{','}') if n['shape']=='decision' else ('[',']')
                lines.append(f'      {nid}{a}"{q(n["label"])}"{b}')
            lines.append('    end')
        lines.append('  end')
    seen=set()
    for f in m['flows']:
        for e in f['edges']:
            key=(e['source'],e['target'],e.get('label',''))
            if e['source'] not in chosen or e['target'] not in chosen or key in seen:continue
            seen.add(key)
            lines.append(f'  {e["source"]} -->|"{q(e.get("label",f["kind"]))}"| {e["target"]}')
    for e in m['dependencies']:
        if e['source'] in chosen and e['target'] in chosen:lines.append(f'  {e["source"]} -. "{q(e["label"])}" .-> {e["target"]}')
    return '\n'.join(lines)+'\n'
(base/'architecture-detail.mmd').write_text(mermaid(),encoding='utf-8')
agent_ids=[n['id'] for n in m['nodes'] if n['group'] in ['agent_graph','agent_capabilities','ai_ports','ai_adapters','llm_services','cache_layer','memory_services','lf_prompts','lf_traces','lf_evals','evaluation_jobs']]
(base/'architecture-agentic.mmd').write_text(mermaid(agent_ids),encoding='utf-8')
# Compact overview keeps the two application paths and all distant services inside infrastructure.
summary='''flowchart TB
  C["Frontend web / mobile / back-office"] --> E["Reverse proxy / WAF / API Gateway"]
  E --> API["Tier 1 · Façade API / DTO / contrôleurs / streaming"]
  subgraph APP["Tier 2 · Application"]
    CLASSIC["Services API classiques / cas d’usage"]
    GRAPH["Workflow agentique / superviseur / conditions"]
    AGENTS["Recherche / analyse / synthèse / relecture"]
    CAPS["Skills / tools / échanges / état partagé"]
    PORTS["Ports LLM / prompts / cache / mémoire / traces / persistance"]
    GRAPH --> AGENTS --> CAPS --> PORTS
  end
  API --> CLASSIC
  API --> GRAPH
  DOMAIN["Tier 3 · Domaine / agrégats / règles / événements"]
  CLASSIC --> DOMAIN
  CLASSIC --> PORTS
  subgraph INFRA["Tier 4 · Infrastructure : adaptateurs internes ET services externes"]
    AD["Adaptateurs : repositories / ORM / clients LLM / checkpointer / tools / Langfuse"]
    DATA[("BDD / cache applicatif / checkpoints / base vectorielle")]
    LLM["LLM / embeddings / LLM évaluateur"]
    CACHE["Cache de réponses LLM / cache local de prompts / hit-miss / versions"]
    subgraph LF["Langfuse · un service, plusieurs capacités"]
      PROMPTS["Prompts / versions / labels"]
      TRACES["Traces / générations / sessions / scores"]
      EVAL["Datasets / expériences / évaluations / feedback"]
    end
    EXT["Recherche / fichiers / identité / paiement / notifications / broker"]
    OPS["Métriques / logs / dashboards / alertes"]
    AD --> DATA
    AD --> CACHE
    AD --> LLM
    AD --> PROMPTS
    AD --> TRACES
    AD --> EXT
    TRACES --> EVAL
    EVAL -->|LLM-as-judge| LLM
    CACHE -->|miss| LLM
    PROMPTS -->|version dans la clé| CACHE
  end
  PORTS --> AD
  AD -. implémente .-> PORTS
  PIPE["CI/CD · tests / images / staging / régressions"] --> RUN["Orchestrateur / réplicas API / workers / secrets / IaC"]
  RUN -->|héberge| API
  EVAL -->|résultats de régression| PIPE
  API -->|télémétrie| AD
'''
(base/'architecture-overview.mmd').write_text(summary,encoding='utf-8')
print(json.dumps(dict(version=m['version'],nodes=len(ids),groups=len(m['groups']),views=len(m['views']),flows=len(m['flows'])),ensure_ascii=False))
