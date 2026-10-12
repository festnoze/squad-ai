(() => {
 const root=document.getElementById('reactor-scene-proposal');
 const area=root.querySelector('[data-projection]'),range=root.querySelector('[data-explode]'),value=root.querySelector('[data-value]');
 const ns='http://www.w3.org/2000/svg';
 function el(tag,attrs={},text){const e=document.createElementNS(ns,tag);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);if(text!==undefined)e.textContent=text;return e;}
 function label(svg,words,x,y,max){let line='',lines=[];for(const word of words.split(' ')){if(line&&(line+' '+word).length>max){lines.push(line);line=word;}else line=(line+' '+word).trim();}if(line)lines.push(line);const t=el('text',{x,y});lines.forEach((l,i)=>t.append(el('tspan',{x,dy:i?16:0},l)));svg.append(t);}
 function draw(){
  const w=Math.max(280,Math.floor(area.getBoundingClientRect().width)),p=Number(range.value)/100;
  const cx=w*.32,footprint=w*.52,h=48+footprint*.045,lx=w*.70,max=Math.max(12,Math.floor((w-lx-6)/6.7));
  const svg=el('svg',{class:'reactor-projection',role:'img','aria-labelledby':'reactor-title reactor-desc'});
  svg.append(el('title',{id:'reactor-title'},'Projection schématique du réacteur modulaire'));
  svg.append(el('desc',{id:'reactor-desc'},'Quatre plateaux : API, application avec agents, domaine et infrastructure. La décomposition écarte les plateaux et les modules du socle. LLM, cache et Langfuse restent rattachés au socle infrastructure. Un rail représente le CI/CD.'));
  const ys=[0,1,2,3].map(i=>86+i*(h+10)+(i-1.5)*p*34);
  const railX=w*.62,railTop=ys[0]-10,railBottom=ys[3]+h+48;
  svg.append(el('line',{x1:railX,y1:railTop,x2:railX,y2:railBottom,stroke:'var(--border)','stroke-width':2}));
  const ay=railTop+(railBottom-railTop-16)*p;
  svg.append(el('rect',{x:railX-6,y:ay,width:12,height:16,rx:2,fill:'var(--viz-series-1)'}));
  label(svg,'Rail CI/CD',railX-32,railBottom+20,12);
  const layers=[['API · façade',.74,'var(--viz-series-1)'],['Application · agents',.93,'var(--viz-series-2)'],['Domaine · noyau',.65,'var(--viz-series-3)'],['Infrastructure',1,'var(--viz-series-4)']];
  // Rear connections stay attached as the plates separate.
  for(let i=0;i<3;i++)svg.append(el('path',{d:`M${cx} ${ys[i]+h*.55} C${cx+25} ${(ys[i]+ys[i+1])/2},${cx+25} ${(ys[i]+ys[i+1])/2},${cx} ${ys[i+1]+h*.4}`,fill:'none',stroke:'var(--viz-series-1)','stroke-width':1.5}));
  layers.forEach(([name,ratio,color],i)=>{
   const fw=footprint*ratio,y=ys[i],left=cx-fw/2,right=cx+fw/2;
   const pts=[[left,y+h*.35],[left+fw*.18,y],[right-fw*.18,y],[right,y+h*.35],[right-fw*.15,y+h*.8],[left+fw*.15,y+h*.8]];
   const bottom=pts.map(([x,yy])=>[x,yy+10]);
   svg.append(el('polygon',{points:bottom.map(a=>a.join(',')).join(' '),fill:'var(--muted)',stroke:'var(--border)','stroke-width':1}));
   svg.append(el('polygon',{points:pts.map(a=>a.join(',')).join(' '),fill:`color-mix(in srgb,${color} 17%,var(--card))`,stroke:'var(--border)','stroke-width':1}));
   svg.append(el('line',{x1:right+3,y1:y+h*.4,x2:lx-8,y2:y+h*.4,stroke:'var(--border)','stroke-width':1}));
   label(svg,name,lx,y+h*.4-4,max);
   if(i===0){for(let j=0;j<3;j++)svg.append(el('rect',{x:cx-fw*.25+j*fw*.18,y:y+h*.25,width:fw*.12,height:13,rx:2,fill:color,opacity:.55}));}
   if(i===1){
    const centerY=y+h*.40;
    for(let j=0;j<4;j++){const angle=j*Math.PI/2+.4,px=cx+Math.cos(angle)*fw*.31,py=centerY+Math.sin(angle)*h*.26;svg.append(el('line',{x1:cx,y1:centerY,x2:px,y2:py,stroke:color,'stroke-width':1.3}));svg.append(el('circle',{cx:px,cy:py,r:Math.max(6,fw*.035),fill:color,opacity:.6}));}
    svg.append(el('circle',{cx,cy:centerY,r:Math.max(7,fw*.042),fill:color}));
   }
   if(i===2){svg.append(el('ellipse',{cx,cy:y+h*.37,rx:fw*.25,ry:h*.27,fill:'var(--card)',stroke:color,'stroke-width':2}));svg.append(el('ellipse',{cx,cy:y+h*.37,rx:fw*.13,ry:h*.14,fill:color,opacity:.7}));}
   if(i===3){
    ['LLM','Cache','LF'].forEach((word,j)=>{
     const mw=fw*.23,x=cx-fw*.36+j*fw*.25+(j-1)*p*fw*.08,yy=y+h*.27+p*15;
     svg.append(el('rect',{x,y:yy,width:mw,height:27,rx:3,fill:'var(--card)',stroke:'var(--border)','stroke-width':1}));
     const t=el('text',{x:x+mw/2,y:yy+18,'text-anchor':'middle'},word);svg.append(t);
    });
    label(svg,'LLM · cache · Langfuse',lx,y+h*.4+38,max);
   }
  });
  const total=railBottom+64;
  svg.setAttribute('viewBox',`0 0 ${w} ${total}`);svg.style.height=total+'px';area.replaceChildren(svg);value.textContent=range.value+' %';
 }
 function restore(s){const n=s?.privateContent?.explode;if(Number.isFinite(n))range.value=Math.min(100,Math.max(0,n));}
 restore(window.openai?.widgetState);
 range.addEventListener('input',draw);
 range.addEventListener('change',()=>window.openai?.setWidgetState?.({modelContent:{proposal:'reacteur-modulaire'},privateContent:{explode:Number(range.value)}}).catch(()=>{}));
 window.addEventListener('openai:set_globals',e=>{restore(e.detail?.globals?.widgetState);draw();});new ResizeObserver(draw).observe(area);draw();
})();
