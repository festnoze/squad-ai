(() => {
 'use strict';
 document.documentElement.classList.add('js');
 const root=document.documentElement,header=document.querySelector('.site-header');
 const menu=document.querySelector('.menu-toggle'),themeButton=document.querySelector('.theme-toggle');
 const motionPreference=window.matchMedia('(prefers-reduced-motion: reduce)');
 const navLinks=[...document.querySelectorAll('.main-nav a')];
 function setMenu(open){header.classList.toggle('menu-is-open',open);menu.setAttribute('aria-expanded',String(open));menu.setAttribute('aria-label',open?'Fermer le menu':'Ouvrir le menu');}
 menu.addEventListener('click',()=>setMenu(!header.classList.contains('menu-is-open')));
 navLinks.forEach(a=>a.addEventListener('click',()=>setMenu(false)));
 document.addEventListener('click',e=>{if(!header.contains(e.target))setMenu(false);});
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&header.classList.contains('menu-is-open')){setMenu(false);menu.focus();}});
 function syncTheme(){const dark=root.dataset.theme==='dark';themeButton.setAttribute('aria-pressed',String(dark));themeButton.setAttribute('aria-label',dark?'Activer le thème clair':'Activer le thème sombre');document.querySelector('meta[name=theme-color]').content=dark?'#1c2a48':'#eff1e8';}
 themeButton.addEventListener('click',()=>{root.dataset.theme=root.dataset.theme==='dark'?'light':'dark';try{localStorage.setItem('em-theme-v2',root.dataset.theme);}catch{}syncTheme();});syncTheme();
 const reveals=[...document.querySelectorAll('.reveal')];
 if('IntersectionObserver' in window){const observer=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){entry.target.classList.add('is-visible');observer.unobserve(entry.target);}}),{threshold:.08,rootMargin:'0px 0px -20px 0px'});reveals.forEach(el=>observer.observe(el));}else reveals.forEach(el=>el.classList.add('is-visible'));
 let scrollScheduled=false;
 const progress=document.querySelector('.reading-progress span');
 function updateScroll(){scrollScheduled=false;header.classList.toggle('is-scrolled',window.scrollY>20);const total=document.documentElement.scrollHeight-window.innerHeight;progress.style.width=(total>0?Math.min(100,Math.max(0,window.scrollY/total*100)):0)+'%';const position=window.scrollY+180;let current='';for(const section of document.querySelectorAll('main>section[id]')){if(section.offsetTop<=position)current=section.id;}navLinks.forEach(a=>{if(a.hash==='#'+current)a.setAttribute('aria-current','location');else a.removeAttribute('aria-current');});}
 function requestScroll(){if(!scrollScheduled){scrollScheduled=true;requestAnimationFrame(updateScroll);}}
 window.addEventListener('scroll',requestScroll,{passive:true});window.addEventListener('resize',requestScroll,{passive:true});updateScroll();
 document.querySelectorAll('details').forEach(d=>d.addEventListener('toggle',requestScroll));
 const dialog=document.querySelector('.mission-dialog'),dialogContent=dialog.querySelector('.dialog-content');let lastOpener=null;
 document.querySelectorAll('[data-open-mission]').forEach(button=>button.addEventListener('click',()=>{const template=document.getElementById('mission-'+button.dataset.openMission);if(!template)return;lastOpener=button;dialogContent.replaceChildren(template.content.cloneNode(true));dialog.showModal();document.body.classList.add('dialog-is-open');}));
 dialog.querySelector('.dialog-close').addEventListener('click',()=>dialog.close());
 dialog.addEventListener('click',e=>{const r=dialog.getBoundingClientRect();if(e.target===dialog&&(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom))dialog.close();});
 dialog.addEventListener('close',()=>{document.body.classList.remove('dialog-is-open');lastOpener?.focus({preventScroll:true});});
 dialog.querySelector('[data-dialog-contact]').addEventListener('click',()=>{dialog.close();setTimeout(()=>document.getElementById('contact').scrollIntoView({behavior:motionPreference.matches?'auto':'smooth'}),0);});
 const toast=document.querySelector('.toast');let toastTimer;
 function notify(message){clearTimeout(toastTimer);toast.textContent=message;toast.classList.add('is-visible');toastTimer=setTimeout(()=>toast.classList.remove('is-visible'),2800);}
 const copyButton=document.querySelector('[data-copy-email]');
 copyButton.addEventListener('click',async()=>{const email=copyButton.dataset.copyEmail;try{if(navigator.clipboard&&window.isSecureContext)await navigator.clipboard.writeText(email);else{const field=document.createElement('textarea');field.value=email;field.setAttribute('readonly','');field.style.cssText='position:fixed;left:-9999px;top:0';document.body.append(field);field.select();const ok=document.execCommand('copy');field.remove();if(!ok)throw new Error('copy');}notify('Adresse e-mail copiée');}catch{notify('Adresse : '+email);}});
 let printStates=[];window.addEventListener('beforeprint',()=>{printStates=[...document.querySelectorAll('details')].map(el=>[el,el.open]);printStates.forEach(([el])=>el.open=true);});window.addEventListener('afterprint',()=>printStates.forEach(([el,open])=>el.open=open));
 // An original 2D generative field; no external library or model is needed.
 const canvas=document.getElementById('intelligence-canvas'),art=canvas.closest('.hero-art');
 const ctx=canvas.getContext('2d');if(!ctx)return;
 const motionButton=art.querySelector('[data-motion]');
 let width=0,height=0,raf=null,inView=true,paused=motionPreference.matches,time=0,last=0,lastPaint=0;
 let pointer={x:0,y:0},follow={x:0,y:0};
 function paint(t){
   ctx.clearRect(0,0,width,height);if(motionPreference.matches){t=0;follow.x=0;follow.y=0;}else{follow.x+=(pointer.x-follow.x)*.06;follow.y+=(pointer.y-follow.y)*.06;}
   const cx=width*.52+follow.x*18,cy=height*.46+follow.y*14,scale=Math.min(width,height)*.47;
   // Fine meridian-like curves form an evolving, woven contour field.
   for(let line=0;line<44;line++){
     const phase=line/44*Math.PI*2;
     ctx.beginPath();
     for(let point=0;point<=128;point++){
       const angle=point/128*Math.PI*2;
       const wave=1+.15*Math.cos(3*angle+phase+t*.14)+.08*Math.sin(5*angle-phase-t*.10);
       const radius=scale*(.26+.72*(line/44))*wave;
       const x=cx+Math.cos(angle)*radius+.14*scale*Math.sin(phase+t*.09);
       const y=cy+Math.sin(angle)*radius*.90+.09*scale*Math.cos(phase-angle*2+t*.12);
       if(point===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);
     }
     ctx.strokeStyle=line%7===0?'rgba(223,246,138,.80)':'rgba(183,200,217,.35)';ctx.lineWidth=line%7===0?1:0.6;ctx.stroke();
   }
   // Small packets follow the same field rather than adding unrelated movement.
   for(let i=0;i<7;i++){
     const angle=t*.13+i*Math.PI*2/7,radius=scale*(.58+.14*Math.sin(i*2.2));
     const x=cx+Math.cos(angle)*radius,y=cy+Math.sin(angle)*radius*.9;
     ctx.beginPath();ctx.arc(x,y,i%3===0?3:1.6,0,Math.PI*2);ctx.fillStyle=i%3===0?'#dff68a':'rgba(255,255,255,.8)';ctx.fill();
   }
 }
 function updateMotionButton(){if(!motionButton)return;const reduced=motionPreference.matches;motionButton.textContent=reduced?'Mouvements réduits':paused?'Relancer ↗':'Pause Ⅱ';motionButton.setAttribute('aria-pressed',String(paused));motionButton.setAttribute('aria-label',reduced?'Animation désactivée selon vos préférences de mouvement':paused?'Relancer l’animation':'Mettre en pause l’animation');motionButton.disabled=reduced;}
 function canRun(){return inView&&!paused&&!motionPreference.matches&&!document.hidden;}
 function frame(now){raf=null;if(!canRun())return;const delta=last?Math.min(now-last,80):0;last=now;time+=delta;if(now-lastPaint>=32){paint(time/1000);lastPaint=now;}raf=requestAnimationFrame(frame);}
 function schedule(){if(canRun()){if(raf===null){last=0;raf=requestAnimationFrame(frame);}}else{if(raf!==null){cancelAnimationFrame(raf);raf=null;}paint(time/1000);}updateMotionButton();}
 function resize(){const rect=art.getBoundingClientRect();width=rect.width;height=rect.height;const dpr=Math.min(window.devicePixelRatio||1,1.8);canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);paint(time/1000);}
 new ResizeObserver(resize).observe(art);resize();
 art.addEventListener('pointermove',e=>{const r=art.getBoundingClientRect();pointer.x=(e.clientX-r.left)/r.width-.5;pointer.y=(e.clientY-r.top)/r.height-.5;},{passive:true});art.addEventListener('pointerleave',()=>pointer={x:0,y:0},{passive:true});
 motionButton?.addEventListener('click',()=>{paused=!paused;schedule();});
 const visibility=new IntersectionObserver(entries=>{inView=entries[0].isIntersecting;schedule();},{threshold:0});visibility.observe(art);
 document.addEventListener('visibilitychange',schedule);motionPreference.addEventListener('change',()=>{paused=motionPreference.matches;schedule();});schedule();
})();
