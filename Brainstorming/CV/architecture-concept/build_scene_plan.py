import json
from pathlib import Path
base=Path(__file__).resolve().parent
m=json.loads((base/'architecture.json').read_text(encoding='utf-8'))
plan={
 'title':'Réacteur modulaire — API et agents',
 'status':'Proposition de scène ; géométrie Blender à créer',
 'units':'metres',
 'visual_direction':{'body':'Graphite sombre, surfaces mates, chanfreins nets','structure':'Titane brossé et pièces usinées','flows':'Trajets cyan ; embranchements et évaluations ambre','lighting':'Éclairage studio, liseré froid et contre-jour chaud','silhouette':'Quatre plateaux octogonaux emboîtés, noyau métier, arène d’agents et socle technique'},
 'hierarchy':[
  {'id':'ROOT','parent':None,'kind':'empty','children':['ENTRY','API','APPLICATION','DOMAIN','INFRASTRUCTURE','DELIVERY']},
  {'id':'ENTRY','parent':'ROOT','kind':'gate','semantic_sections':['clients','edge'],'shape':'Sas et antennes clients','explode':[0,0,0.4]},
  {'id':'API','parent':'ROOT','kind':'plate','semantic_sections':['api'],'shape':'Capot octogonal et façade à filtres','z':2.7,'explode':[0,0,1.6]},
  {'id':'APPLICATION','parent':'ROOT','kind':'plate','semantic_sections':['app'],'shape':'Deux secteurs : services classiques et arène d’agents','z':1.8,'explode':[0,0,0.8]},
  {'id':'DOMAIN','parent':'ROOT','kind':'core','semantic_sections':['domain'],'shape':'Cylindre central, anneaux segmentés et noyau stable','z':0.9,'explode':[0,0,0]},
  {'id':'INFRASTRUCTURE','parent':'ROOT','kind':'base','semantic_sections':['infra'],'shape':'Socle à tiroirs ; adaptateurs et services distants gardent le même parent','z':0,'explode':[0,0,-0.8]},
  {'id':'DELIVERY','parent':'ROOT','kind':'rail','semantic_sections':['delivery'],'shape':'Rail vertical, artefact mobile et socle de déploiement','explode':[1.6,0,0]},
  {'id':'AGENT_ARENA','parent':'APPLICATION','kind':'radial_assembly','shape':'Superviseur central, agents périphériques, aiguillages conditionnels','children':['POD_SUPERVISOR','POD_RESEARCH','POD_ANALYSIS','POD_SYNTHESIS','POD_REVIEW']},
  {'id':'LANGFUSE','parent':'INFRASTRUCTURE','kind':'cartridge','shape':'Un seul boîtier à trois faces : prompts, traces, évaluations','semantic_groups':['lf_prompts','lf_traces','lf_evals','evaluation_jobs'],'explode':[0,-1.2,0]},
  {'id':'LLM_SERVICES','parent':'INFRASTRUCTURE','kind':'cartridge','shape':'Cartouches modèles, embeddings et judge','semantic_groups':['llm_services'],'explode':[-1.2,0,0]},
  {'id':'CACHE_SERVICES','parent':'INFRASTRUCTURE','kind':'cartridge','shape':'Mémoire rapide, aiguillage hit / miss et stockage distinct des checkpoints','semantic_groups':['cache_layer','memory_services'],'explode':[1.2,0,0]}
 ],
 'agent_instances':[
  {'id':asset,'parent':'AGENT_ARENA','semantic_node':nid,'children':['ROLE_CONTEXT','SKILLS','TOOLS','MESSAGES','PORTS'],'geometry_shared':'agent_pod','explode_mode':'radial'}
  for asset,nid in [('POD_SUPERVISOR','supervisor'),('POD_RESEARCH','research_agent'),('POD_ANALYSIS','analyst_agent'),('POD_SYNTHESIS','writer_agent'),('POD_REVIEW','review_agent')]
 ],
 'part_mapping':[{'semantic_node':n['id'],'asset_id':{'supervisor':'POD_SUPERVISOR','research_agent':'POD_RESEARCH','analyst_agent':'POD_ANALYSIS','writer_agent':'POD_SYNTHESIS','review_agent':'POD_REVIEW'}.get(n['id'],'part_'+n['id']),'logical_parent':n['section'],'assembly_parent':{'clients':'ENTRY','edge':'ENTRY','api':'API','app':'APPLICATION','domain':'DOMAIN','infra':'INFRASTRUCTURE','delivery':'DELIVERY'}[n['section']],'subassembly':n['group'],'geometry':'switch' if n['shape']=='decision' else 'module'} for n in m['nodes']],
 'navigation':[
  {'mode':'Scroll narratif','behavior':'Progression déterministe de la caméra et de la décomposition ; retour parfaitement réversible.'},
  {'mode':'Focus au clic','behavior':'Centrer et cadrer l’assemblage sélectionné ; conserver un repère vers la vue globale.'},
  {'mode':'Inspection libre','behavior':'Rotation orbitale, zoom borné et sélection des pièces ; la molette est réservée à ce mode lorsqu’il est activé.'},
  {'mode':'Décomposition','behavior':'Curseur d’ouverture global puis local : plateau → agent → skills / tools ; socle → Langfuse → capacités.'}
 ],
 'scroll_storyboard':m['scroll'],
 'flow_representation':{'mesh':'Courbes ou tubes simples pour les connecteurs','animation':'Paquets lumineux suivant les arêtes du modèle ; seul le scénario actif est détaillé','anchoring':'Extrémités attachées à des ports nommés sur les pièces, recalculées pendant le mouvement','semantic_styles':{'request':'continu','agent_message':'paquet entre pods','conditional':'aiguillage allumé','telemetry':'signal vers Langfuse','evaluation':'retour de score','cache':'bifurcation hit / miss'}},
 'blender_authoring':{'workflow':'Script Python paramétrique ; primitives, répétitions, chanfreins, UV et matériaux PBR','collections':'Hiérarchie identique au plan de scène ; noms stables et pivots locaux','animation':'Translations et rotations des pièces ; assemblage / éclatement / focus stockés séparément','deliverables':['reactor-api.blend','reactor-api.glb','scene-manifest.json'],'labels':'Libellés détaillés en surimpression web, associés aux IDs de pièces'},
 'web_runtime':{'format':'GLB / glTF 2.0','rendering':'Three.js ou React Three Fiber','drivers':'Un paramètre de scroll commun pour la caméra, les poses et les connecteurs','effects':'Halo limité aux trajets actifs ; éviter de superposer des coques transparentes complètes','accessibility':'Réduire les mouvements selon la préférence utilisateur ; conserver le contenu du CV en HTML'},
 'performance_targets':{'status':'Budgets de conception à valider après export','triangles':[60000,100000],'glb_megabytes':[2,5],'strategies':['Réutiliser la géométrie des pods et des petites pièces','Baker les détails de surface utiles','Limiter les textures et les matériaux','Niveaux de détail pour les sous-pièces','Arrêter le rendu hors écran']}
}
(base/'blender-scene-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Scene proposal saved:',len(plan['part_mapping']),'semantic mappings')
