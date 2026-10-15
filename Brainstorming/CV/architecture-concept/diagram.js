(() => {
  const root=document.getElementById('architecture-api-explorer');
  const model=JSON.parse(root.querySelector('[data-model]').textContent);
  const focus=root.querySelector('[data-focus]'),flow=root.querySelector('[data-flow]');
  const area=root.querySelector('[data-diagram]'),detail=root.querySelector('[data-detail]'),legend=root.querySelector('[data-legend]');
  const nodes=new Map(model.nodes.map(n=>[n.id,n])),groups=new Map(model.groups.map(g=>[g.id,g]));
  const ns='http://www.w3.org/2000/svg';
  function el(tag,attrs={},value) {const e=document.createElementNS(ns,tag);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);if(value!==undefined)e.textContent=value;return e;}
  function wrap(value,max) {let line='';const out=[];for(const word of value.split(' ')){if(line&&(line+' '+word).length>max){out.push(line);line=word;}else line=(line+' '+word).trim();}if(line)out.push(line);return out;}
  function text(svg,value,x,y,max,cls='',anchor='start') {const a=wrap(value,max),t=el('text',{x,y,class:cls,'text-anchor':anchor});a.forEach((line,i)=>t.append(el('tspan',{x,dy:i?16:0},line)));svg.append(t);return a.length*16;}
  const initialFlow={all:'agentic',entry:'command',api:'command',app:'command',agentic:'agentic',agent:'agent',domain:'command',infra:'llm_miss',llm:'llm_miss',cache:'llm_hit',langfuse:'langfuse',services:'llm_miss',ops:'telemetry',delivery:'delivery'};
  function restore(state){const s=state?.modelContent;if(s?.version!==2)return;if(model.views.some(v=>v.id===s.focus))focus.value=s.focus;if(model.flows.some(f=>f.id===s.flow))flow.value=s.flow;}
  function draw(){
    const width=Math.max(280,Math.floor(area.getBoundingClientRect().width)),margin=14,gap=18;
    const view=model.views.find(v=>v.id===focus.value),active=model.flows.find(f=>f.id===flow.value);
    const cols=width>=620?3:width>=440?2:1,cardWidth=(width-margin*2-gap*(cols-1))/cols;
    const max=Math.max(20,Math.floor((cardWidth-22)/6.8));
    const selectedGroups=model.groups.filter(g=>view.sections.includes(g.section)||view.groups.includes(g.id));
    const visibleIds=new Set(selectedGroups.flatMap(g=>g.nodes));
    const activeIds=new Set(active.edges.flatMap(e=>[e.source,e.target]));
    const aliases=new Map(),positions=new Map(),links=new Map();
    const svg=el('svg',{class:'architecture-diagram',role:'img','aria-labelledby':'architecture-graph-title architecture-graph-description'});
    svg.append(el('title',{id:'architecture-graph-title'},view.label));
    svg.append(el('desc',{id:'architecture-graph-description'},'API à quatre couches. Les workflows et agents sont applicatifs. Tous les services distants LLM, cache, prompts, Langfuse, données et observabilité appartiennent à l’infrastructure. Les losanges désignent les conditions ; les pointillés courts les dépendances de code.'));
    const defs=el('defs');
    for(const[id,color]of[['active','var(--viz-series-1)'],['dependency','var(--muted-foreground)']]){const m=el('marker',{id:'architecture-arrow-'+id,viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:5,markerHeight:5,orient:'auto-start-reverse'});m.append(el('path',{d:'M0 0 L10 5 L0 10 z',fill:color}));defs.append(m);}svg.append(defs);
    const edges=el('g'),marks=el('g');svg.append(edges,marks);let y=8;
    function row(items,subtitle={}){
      const cw=(width-margin*2-gap*(items.length-1))/items.length;
      const cm=Math.max(20,Math.floor((cw-22)/6.8));
      const heights=items.map(n=>n.shape==='decision'?104:wrap(n.label,cm).length*16+(n.count?40:26)+(subtitle[n.id]?wrap(subtitle[n.id],cm).length*16+7:0));
      const h=Math.max(...heights);
      items.forEach((n,j)=>{
        const x=margin+j*(cw+gap),g=el('g',{'data-node-id':n.id});
        const isActive=n.members?n.members.some(id=>activeIds.has(id)):activeIds.has(n.id);
        const cls='component'+(isActive?' active-component':'');
        if(n.shape==='decision'){
          g.append(el('polygon',{points:`${x+cw/2},${y} ${x+cw},${y+h/2} ${x+cw/2},${y+h} ${x},${y+h/2}`,class:cls}));
          const dm=Math.max(16,Math.floor(cw*.62/6.8)),a=wrap(n.label,dm);
          text(g,n.label,x+cw/2,y+h/2-(a.length-1)*8+4,dm,'','middle');
        }else{
          g.append(el('rect',{x,y,width:cw,height:h,rx:5,class:cls}));
          const th=text(g,n.label,x+11,y+21,cm);
          if(n.count)text(g,n.count+' composants',x+11,y+21+th+3,cm,'secondary');
          if(subtitle[n.id])text(g,subtitle[n.id],x+11,y+21+th+6,cm,'secondary');
        }
        marks.append(g);positions.set(n.id,{x,y,w:cw,h});
      });
      y+=h+28;
    }
    for(const section of model.sections){
      const sg=selectedGroups.filter(g=>g.section===section.id);
      const overview=model.overview.find(o=>o.section===section.id);
      if(view.id!=='all'&&!sg.length)continue;
      y+=text(marks,section.label,margin,y+12,Math.floor((width-2*margin)/6.8),'section-label')+16;
      marks.append(el('line',{x1:margin,y1:y-7,x2:width-margin,y2:y-7,stroke:'var(--border)','stroke-width':1}));
      if(view.id==='all'){
        const items=overview.items.map(([id,label,gids])=>{const members=gids.flatMap(gid=>groups.get(gid).nodes);members.forEach(nid=>aliases.set(nid,id));return{id,label,count:members.length,members};});
        for(let i=0;i<items.length;i+=cols)row(items.slice(i,i+cols));
      }else if(view.id==='agentic'){
        const rows=[['agent_run','graph_state'],['supervisor','run_budget'],['route_decision'],['research_agent','analyst_agent','writer_agent'],['review_agent'],['quality_gate'],['run_output','run_failed']];
        const subs={research_agent:'Si recherche nécessaire',analyst_agent:'Si analyse nécessaire',writer_agent:'Si contexte suffisant',run_output:'Si validé',run_failed:'Si budget atteint'};
        for(const r of rows)for(let i=0;i<r.length;i+=cols)row(r.slice(i,i+cols).map(id=>nodes.get(id)),subs);
      }else{
        for(const g of sg){
          const gl=g.label+(g.scope==='remote'?' · service externe':'');
          y+=text(marks,gl,margin,y+12,Math.floor((width-2*margin)/6.8),'secondary')+12;
          for(let i=0;i<g.nodes.length;i+=cols)row(g.nodes.slice(i,i+cols).map(id=>nodes.get(id)));
          y+=6;
        }
      }
      y+=12;
    }
    const mapId=id=>view.id==='all'?aliases.get(id):id;
    for(const e of active.edges){const a=mapId(e.source),b=mapId(e.target),key=a+'>'+b;if(a&&b&&a!==b&&positions.has(a)&&positions.has(b)&&!links.has(key))links.set(key,{a,b,dependency:false,label:e.label||''});}
    if(['all','app','agent','infra'].includes(view.id))for(const e of model.dependencies){const a=mapId(e.source),b=mapId(e.target),key=a+'>'+b;if(a&&b&&a!==b&&positions.has(a)&&positions.has(b)&&!links.has(key))links.set(key,{a,b,dependency:true,label:e.label});}
    let lane=0;
    for(const{a:aid,b:bid,dependency,label}of links.values()){
      const a=positions.get(aid),b=positions.get(bid);let path;
      if(Math.abs(a.y-b.y)<2){const right=b.x>a.x,sx=right?a.x+a.w:a.x,tx=right?b.x:b.x+b.w;path=`M${sx} ${a.y+a.h/2} L${tx} ${b.y+b.h/2}`;}
      else{const down=b.y>a.y,sx=a.x+a.w/2,sy=down?a.y+a.h:a.y,tx=b.x+b.w/2,ty=down?b.y:b.y+b.h;if(Math.abs(sx-tx)<1&&Math.abs(sy-ty)<85)path=`M${sx} ${sy} L${tx} ${ty}`;else{const rail=down?width-3-(lane%4)*2:3+(lane%4)*2,sign=down?1:-1;lane++;path=`M${sx} ${sy} L${sx} ${sy+sign*11} L${rail} ${sy+sign*11} L${rail} ${ty-sign*11} L${tx} ${ty-sign*11} L${tx} ${ty}`;}}
      const p=el('path',{d:path,class:'connection '+(dependency?'dependency':active.kind==='event'?'active event':'active'),'marker-end':'url(#architecture-arrow-'+(dependency?'dependency':'active')+')'});p.append(el('title',{},label||active.label));edges.append(p);
    }
    const annotations=[];
    if(view.id==='agentic')annotations.push('Retour relecteur → synthèse : à réviser et budget disponible.','Échanges analyse ↔ recherche : résultats et demandes de complément.');
    if(view.id!=='all')for(const e of active.edges)if(visibleIds.has(e.source)!==visibleIds.has(e.target))annotations.push(nodes.get(e.source).label+' → '+nodes.get(e.target).label);
    if(annotations.length){y+=text(marks,'Transitions et connexions',margin,y+12,Math.floor((width-2*margin)/6.8),'section-label')+14;for(const line of [...new Set(annotations)])y+=text(marks,line,margin,y+12,Math.floor((width-2*margin)/6.8),'secondary')+10;}
    svg.setAttribute('viewBox',`0 0 ${width} ${y+4}`);svg.style.height=(y+4)+'px';area.replaceChildren(svg);
    detail.textContent=view.id==='all'?`${model.nodes.length} composants · 4 couches logiques · services externes dans l’infrastructure`:view.label;
    legend.replaceChildren();
    for(const[label,cls]of[[active.label,active.kind==='event'?' event':''],['Dépendance de code',' dependency']]){const s=document.createElement('span'),mark=document.createElement('span');mark.className='legend-mark'+cls;s.append(mark,document.createTextNode(label));legend.append(s);}
  }
  function save(){draw();window.openai?.setWidgetState?.({modelContent:{version:2,focus:focus.value,flow:flow.value},privateContent:null}).catch(()=>{});}
  restore(window.openai?.widgetState);
  focus.addEventListener('change',()=>{flow.value=initialFlow[focus.value];save();});flow.addEventListener('change',save);
  window.addEventListener('openai:set_globals',e=>{restore(e.detail?.globals?.widgetState);draw();});new ResizeObserver(draw).observe(area);draw();
})();
