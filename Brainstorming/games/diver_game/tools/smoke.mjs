/**
 * ABYSSE - end to end smoke test.
 *
 * Boots the game in headless Chrome over the DevTools protocol and drives the
 * whole progression: kill, collect, unload, surface, debrief, medal, wetsuit,
 * dive again. Then it checks the predators, the death and respawn path, the
 * codex screens and the ten species milestone.
 *
 * Usage (the static server has to be running already):
 *
 *     python serve.py
 *     node tools/smoke.mjs [url]
 *
 * Exits non zero when a check fails, so it works in a pipeline. Screenshots
 * land in .smoke/ next to the game.
 *
 * Note on timing: headless Chrome falls back to a software renderer, which
 * runs this scene at well under one frame per second. No step here waits out a
 * number of milliseconds hoping the game caught up: every wait is a `T.until`
 * on something observable, and every rate is measured against `game.time`, the
 * clock the simulation itself runs on. The only real time in the file is the
 * 60 ms a synthetic key is held down, which is the key press itself.
 */

import { spawn } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const SHOT_DIR = join(HERE, '..', '.smoke');
mkdirSync(SHOT_DIR, { recursive: true });

const CHROME_CANDIDATES = [
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  (process.env.LOCALAPPDATA || '') + '\\Google\\Chrome\\Application\\chrome.exe',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
];

const CHROME = CHROME_CANDIDATES.find((p) => p && existsSync(p));
if (!CHROME) {
  console.error('Chrome introuvable. Chemins testes:\n  ' + CHROME_CANDIDATES.join('\n  '));
  process.exit(2);
}

const url = process.argv[2] || 'http://localhost:8095/index.html';
const port = 9700 + Math.floor(Date.now() % 200);
const profile = mkdtempSync(join(tmpdir(), 'abysse-smoke-'));

const chrome = spawn(CHROME, [
  '--headless=new',
  '--remote-debugging-port=' + port,
  '--user-data-dir=' + profile,
  '--no-first-run',
  '--no-default-browser-check',
  '--disable-extensions',
  '--mute-audio',
  '--window-size=1440,860',
  '--use-gl=angle',
  '--use-angle=swiftshader',
  '--enable-unsafe-swiftshader',
  '--disable-gpu-sandbox',
  'about:blank',
], { stdio: ['ignore', 'ignore', 'pipe'] });

let chromeErr = '';
chrome.stderr.on('data', (d) => { chromeErr += d.toString(); });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function findTarget() {
  for (let i = 0; i < 80; i++) {
    try {
      const list = await (await fetch('http://127.0.0.1:' + port + '/json/list')).json();
      const page = list.find((t) => t.type === 'page');
      if (page && page.webSocketDebuggerUrl) return page.webSocketDebuggerUrl;
    } catch (err) {
      void err;
    }
    await sleep(250);
  }
  throw new Error('Chrome n a pas expose de cible de debogage.\n' + chromeErr.slice(0, 800));
}

const ws = new WebSocket(await findTarget());
await new Promise((res, rej) => {
  ws.addEventListener('open', res, { once: true });
  ws.addEventListener('error', rej, { once: true });
});

let nextId = 1;
const pending = new Map();
const jsErrors = [];

ws.addEventListener('message', (event) => {
  const msg = JSON.parse(event.data);
  if (msg.id && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    if (msg.error) reject(new Error(JSON.stringify(msg.error)));
    else resolve(msg.result);
    return;
  }
  if (msg.method === 'Runtime.exceptionThrown') {
    const d = msg.params.exceptionDetails;
    jsErrors.push('[EXCEPTION] ' + ((d.exception && d.exception.description) || d.text));
  } else if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') {
    jsErrors.push('[console.error] ' + msg.params.args.map((a) => a.value || a.description).join(' '));
  }
});

function send(method, params) {
  const id = nextId++;
  ws.send(JSON.stringify({ id, method, params: params || {} }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

async function evaluate(expression) {
  const r = await send('Runtime.evaluate', {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (r.exceptionDetails) {
    const d = r.exceptionDetails;
    throw new Error('evaluate: ' + ((d.exception && d.exception.description) || d.text));
  }
  return r.result.value;
}

/** Run an async body in the page with `T` (helpers) and `g` (game) in scope. */
function run(body) {
  return evaluate('(async()=>{const T=window.__t;const g=window.__abysse;' + body + '})()')
    .then((v) => (typeof v === 'string' ? JSON.parse(v) : v));
}

async function screenshot(name) {
  try {
    const s = await send('Page.captureScreenshot', { format: 'png' });
    writeFileSync(join(SHOT_DIR, name + '.png'), Buffer.from(s.data, 'base64'));
  } catch (err) {
    void err;
  }
}

const results = [];
function check(label, ok, detail) {
  results.push({ ok: !!ok, label, detail: detail === undefined ? '' : String(detail) });
}

function finish() {
  const failed = results.filter((r) => !r.ok);
  console.log('\n===== ABYSSE, test de bout en bout =====\n');
  for (const r of results) {
    console.log((r.ok ? '  ok    ' : '  ECHEC ') + r.label + (r.detail ? '  (' + r.detail + ')' : ''));
  }
  console.log('\n  ' + (results.length - failed.length) + ' / ' + results.length + ' verifications passees');
  console.log('  ' + jsErrors.length + ' erreur(s) JavaScript');
  for (const e of jsErrors.slice(0, 20)) console.log('    ' + e);
  console.log('');
  try {
    ws.close();
  } catch (err) {
    void err;
  }
  chrome.kill();
  process.exit(failed.length === 0 && jsErrors.length === 0 ? 0 : 1);
}

await send('Runtime.enable');
await send('Page.enable');
await send('Page.navigate', { url });

// ---------------------------------------------------------------------------
// Boot, from a clean save
// ---------------------------------------------------------------------------

const boot = await evaluate(`(async()=>{
  const w=(ms)=>new Promise(r=>setTimeout(r,ms));
  for(let i=0;i<120 && !window.__abysse;i++) await w(1000);
  if(!window.__abysse) return "TIMEOUT au demarrage";
  localStorage.removeItem("abysse.save.v1");
  window.__abysse.game.save = {version:1,discovered:{},medals:0,medalsSpent:0,pendingSkinPicks:0,
    skins:["standard"],currentSkin:"standard",bestDepth:0,totalKills:0,totalDives:0,credits:0,
    expeditionBonusClaimed:false};
  window.__t = {
    w,
    async until(fn, seconds){
      const end=Date.now()+seconds*1000;
      while(Date.now()<end){ try{ if(fn()) return true; }catch(e){ void e; } await w(250); }
      return false;
    },
    prompt(){
      const p=document.getElementById("prompt");
      return p.classList.contains("hidden") ? "" : document.getElementById("prompt-text").textContent;
    },
    async key(code){
      window.dispatchEvent(new KeyboardEvent("keydown",{code}));
      await w(60);
      window.dispatchEvent(new KeyboardEvent("keyup",{code}));
    },
    visible(id){ return !document.getElementById(id).classList.contains("hidden"); },
  };
  document.getElementById("btn-play").click();
  await window.__t.until(()=>window.__abysse.game.state==="play", 40);
  return "ok state=" + window.__abysse.game.state;
})()`);
check('demarrage de la plongee', boot.startsWith('ok'), boot);
if (!boot.startsWith('ok')) finish();

// ---------------------------------------------------------------------------
// 1. Kill, collect, unload
// ---------------------------------------------------------------------------

const kill = await run(`
  for(let i=0;i<10;i++) g.fauna.stream(g.diver.position);
  const wanted=[]; const seen=new Set();
  for(const c of g.fauna.creatures){
    if(!seen.has(c.speciesId)){ seen.add(c.speciesId); wanted.push(c); }
    if(wanted.length>=3) break;
  }
  const ids=wanted.map(c=>c.speciesId);
  for(const c of wanted) g.fauna.damage(c, c.maxHealth*3, {knockback:0, from:g.diver.position, stun:0});
  await T.until(()=>g.fauna.specimens.length>=wanted.length, 40);
  return JSON.stringify({ids, specimens:g.fauna.specimens.length, alive:wanted.filter(c=>c.alive).length});
`);
check('trois creatures abattues', kill.alive === 0, kill.ids.join(', '));
check('specimens laisses au fond', kill.specimens >= 3, 'specimens=' + kill.specimens);

const net = await run(`
  for(let n=0;n<8;n++){
    const s=g.fauna.specimens.find(x=>!x.collected);
    if(!s) break;
    const before=g.diver.net.length;
    g.diver.teleport(g.diver.position.copy(s.position));
    await T.until(()=>g.diver.net.length>before, 40);
  }
  return JSON.stringify({net:g.diver.net.length, items:g.diver.net.map(i=>i.speciesId)});
`);
check('specimens ramasses au filet', net.net >= 3, 'filet=' + net.net);

// Docking has to work from anywhere around the hull, not only next to the
// cargo hatch. Approach from the bow, which is the far end of the sub.
const bow = await run(`
  const p=g.diver.position;
  const nose=g.sub.axisA.clone();
  const dir=g.sub.axisB.clone().sub(g.sub.axisA).normalize();
  // Four metres ahead of the nose, off to one side.
  g.diver.teleport(p.copy(nose).addScaledVector(dir,-4).add(new p.constructor(3,1,0)));
  const shown=await T.until(()=>T.prompt().length>0, 60);
  return JSON.stringify({shown, prompt:T.prompt(),
    dist:+g.sub.distanceTo(g.diver.position).toFixed(1)});
`);
check('amarrage possible par l avant', bow.shown === true,
  bow.prompt + ' a ' + bow.dist + ' m de l axe');

const unload = await run(`
  g.diver.teleport(g.diver.position.copy(g.sub.dockPoint));
  await T.until(()=>/Decharger/.test(T.prompt()), 60);
  const prompt=T.prompt();
  await T.key("KeyE");
  await T.until(()=>g.sub.cargo.length>0, 60);
  await T.until(()=>/Remonter/.test(T.prompt()), 60);
  return JSON.stringify({prompt, cargo:g.sub.cargo.length, net:g.diver.net.length, next:T.prompt()});
`);
check('invite de dechargement', /Decharger/.test(unload.prompt), unload.prompt);
check('specimens mis en soute', unload.cargo >= 3, 'soute=' + unload.cargo);
check('filet vide apres le depot', unload.net === 0);
check('invite de remontee', /Remonter/.test(unload.next), unload.next);

// ---------------------------------------------------------------------------
// 2. Surface with the submarine
// ---------------------------------------------------------------------------

const surface = await run(`
  await T.key("KeyE");
  const started=await T.until(()=>g.game.state==="transit"||g.sub.state==="ascending", 60);
  // The trip runs on accumulated game time and this renderer is very slow, so
  // fast forward rather than wait out several real minutes for a 3.4 s ride.
  await T.until(()=>{ if(g.sub.state==="ascending") g.sub.transitT=0.99; return g.sub.state==="surface"; }, 150);
  await T.until(()=>g.diver.mode==="walk", 60);
  return JSON.stringify({started, subState:g.sub.state, state:g.game.state, mode:g.diver.mode,
    ground:+g.world.heightAt(g.diver.position.x,g.diver.position.z).toFixed(2)});
`);
check('transit declenche', surface.started === true, 'etat=' + surface.state);
check('sous-marin amarre au ponton', surface.subState === 'surface');
check('debarquement sur sol sec', surface.mode === 'walk' && surface.ground > 0.4,
  'mode=' + surface.mode + ' sol=' + surface.ground);
await screenshot('ile');

// ---------------------------------------------------------------------------
// 3. Scientist debrief, medals, wetsuit
// ---------------------------------------------------------------------------

const debrief = await run(`
  const sci=g.world.points.scientist; const p=g.diver.position;
  g.diver.teleport(p.set(sci.x+2.5, g.world.heightAt(sci.x+2.5, sci.z+2.5)+0.9, sci.z+2.5));
  await T.until(()=>/Presenter/.test(T.prompt()), 60);
  const prompt=T.prompt();
  await T.key("KeyE");
  const open=await T.until(()=>T.visible("scientist"), 60);
  return JSON.stringify({prompt, open, medals:g.game.save.medals,
    discovered:Object.keys(g.game.save.discovered).length,
    pending:g.game.save.pendingSkinPicks, cargo:g.sub.cargo.length});
`);
check('invite du laboratoire', /Presenter/.test(debrief.prompt), debrief.prompt);
check('panneau de debrief ouvert', debrief.open === true);
check('especes entrees au catalogue', debrief.discovered >= 3, 'catalogue=' + debrief.discovered);
check('une medaille par espece inedite', debrief.medals >= 3, 'medailles=' + debrief.medals);
check('choix de combinaison accorde', debrief.pending >= 1, 'en attente=' + debrief.pending);
check('soute videe par la scientifique', debrief.cargo === 0);
await screenshot('scientifique');

const skin = await run(`
  const cont=document.getElementById("sci-continue");
  // The first click skips the typewriter, which is what flips the label to
  // "Continuer". Waiting on the label rather than on a delay: the dialogue is
  // typed on an interval that this renderer starves.
  await T.until(()=>{ if(cont.textContent!=="Continuer") cont.click();
    return cont.textContent==="Continuer"; }, 60);
  cont.click();
  const open=await T.until(()=>T.visible("skins"), 60);
  const locked=[...document.querySelectorAll("#skin-grid > *")].find(c=>c.dataset.owned==="0");
  if(!locked) return JSON.stringify({open, error:"aucune combinaison verrouillee affichee"});
  // Selecting a card is what enables the confirm button, so wait for that.
  locked.click();
  const armed=await T.until(()=>!document.getElementById("skin-confirm").disabled, 60);
  if(!armed) return JSON.stringify({open, error:"le bouton de confirmation reste desactive"});
  document.getElementById("skin-confirm").click();
  await T.until(()=>g.game.save.skins.length>1, 60);
  await T.until(()=>g.game.state==="play", 60);
  return JSON.stringify({open, skins:g.game.save.skins, current:g.game.save.currentSkin,
    pending:g.game.save.pendingSkinPicks, state:g.game.state});
`);
check('selecteur de combinaison ouvert', skin.open === true, skin.error || '');
check('combinaison debloquee', skin.skins && skin.skins.length >= 2, (skin.skins || []).join(', '));
check('combinaison equipee', skin.current && skin.current !== 'standard', skin.current);
check('recompense consommee', skin.pending === 0);
check('retour au jeu apres le choix', skin.state === 'play', skin.state);
await screenshot('combinaisons');

// ---------------------------------------------------------------------------
// 4. Persistence and the trip back down
// ---------------------------------------------------------------------------

const back = await run(`
  const stored=JSON.parse(localStorage.getItem("abysse.save.v1")||"null");
  const land=g.world.points.dockLanding; const p=g.diver.position;
  g.diver.teleport(p.set(land.x, g.world.heightAt(land.x, land.z)+0.9, land.z));
  await T.until(()=>/Redescendre/.test(T.prompt()), 60);
  const prompt=T.prompt();
  await T.key("KeyE");
  await T.until(()=>{ if(g.sub.state==="descending") g.sub.transitT=0.99; return g.sub.state==="deep"; }, 150);
  await T.until(()=>g.diver.mode==="swim" && g.game.state==="play", 60);
  return JSON.stringify({saved: stored && {medals:stored.medals, skins:stored.skins.length,
    discovered:Object.keys(stored.discovered).length},
    prompt, subState:g.sub.state, mode:g.diver.mode, depth:+g.diver.depth.toFixed(1)});
`);
check('progression ecrite dans le localStorage',
  back.saved && back.saved.medals >= 3 && back.saved.skins >= 2 && back.saved.discovered >= 3,
  JSON.stringify(back.saved));
check('invite de redescente', /Redescendre/.test(back.prompt), back.prompt);
check('retour sur le recif en plongee',
  back.subState === 'deep' && back.mode === 'swim' && back.depth > 10,
  'profondeur=' + back.depth);

// ---------------------------------------------------------------------------
// 5. Predators actually hurt the diver
// ---------------------------------------------------------------------------

const predator = await run(`
  for(let i=0;i<12;i++) g.fauna.stream(g.diver.position);
  const shark=g.fauna.creatures.find(c=>c.species.danger===2);
  if(!shark) return JSON.stringify({skipped:true});
  const before=g.diver.health;
  let hits=0, damage=0;
  const prev=g.fauna.onDiverAttacked;
  g.fauna.onDiverAttacked=(c,d)=>{ hits++; damage+=d; if(prev) prev(c,d); };
  // The predator ramps up over several seconds of game time, and this renderer
  // runs at well under a frame per second. Drop it straight into its charge and
  // hold it on the diver so the bite actually lands.
  const ok=await T.until(()=>{
    shark.mode="charge"; shark.modeT=0; shark.cooldownT=0;
    shark.position.copy(g.diver.position); shark.position.y+=1.0;
    return hits>0;
  }, 120);
  g.fauna.onDiverAttacked=prev;
  return JSON.stringify({skipped:false, ok, hits, damage:+damage.toFixed(1),
    species:shark.speciesId, contact:shark.species.contactDamage,
    lost:+(before-g.diver.health).toFixed(1)});
`);
check('un predateur mord le plongeur',
  predator.skipped || (predator.hits > 0 && predator.damage > 0),
  predator.skipped
    ? 'aucun predateur apparu'
    : predator.species + ', ' + predator.hits + ' morsure(s), ' + predator.damage + ' degats');

// ---------------------------------------------------------------------------
// 5b. The net gun captures small fish alive and only tangles the big ones
// ---------------------------------------------------------------------------

const netgun = await run(`
  const save=g.game.save;
  g.diver.net.length=0;
  for(let i=0;i<4;i++) g.fauna.stream(g.diver.position);
  const small=g.fauna.creatures.filter(c=>c.alive && c.species.size<=1.6 && c.species.danger<2);
  if(small.length===0) return JSON.stringify({skipped:true});
  // Bunch a few small fish together and drop the net on them.
  const spot=g.diver.position.clone();
  spot.y += 0.5;
  for(let i=0;i<Math.min(3,small.length);i++){
    small[i].position.copy(spot);
    small[i].position.x += i*0.4;
  }
  const killsBefore=save.totalKills;
  const weapon=g.diver.weapons.find(w=>w.def.id==="netgun");
  const specimensBefore=g.fauna.specimens.length;
  g.diver.hooks.onNetDeploy(spot, weapon.def);
  // The capsule must be visible straight away, the way any other catch is.
  const capsules=g.fauna.specimens.filter(x=>!x.collected && x.object.visible).length;
  const magneted=g.fauna.specimens.filter(x=>x._magnet).length;
  // Then it is reeled in to the diver and lands in the bag on its own.
  const arrived=await T.until(()=>g.diver.net.length>0, 150);
  const caught=g.diver.net.length;
  // Now a predator, which must survive and only be stunned.
  const big=g.fauna.creatures.find(c=>c.alive && c.species.danger===2);
  let bigAlive=null, bigStunned=null;
  if(big){
    const p2=big.position.clone();
    g.diver.hooks.onNetDeploy(p2, weapon.def);
    bigAlive=big.alive;
    bigStunned=big.stunT>0 || big.state==="stunned";
  }
  return JSON.stringify({skipped:false, caught, slot:!!weapon, capsules, magneted, arrived,
    specimensBefore, kills:save.totalKills-killsBefore, bigAlive, bigStunned});
`);
check('lance-filet present comme 4e outil', netgun.skipped || netgun.slot === true);
check('la capsule apparait a la capture',
  netgun.skipped || netgun.capsules > 0, 'capsules visibles=' + netgun.capsules);
check('la capsule est ramenee vers le plongeur',
  netgun.skipped || netgun.magneted > 0, 'aimantees=' + netgun.magneted);
check('le filet capture des petits poissons vivants',
  netgun.skipped || netgun.caught > 0, 'captures=' + netgun.caught);
check('une capture au filet ne compte pas comme une mise a mort',
  netgun.skipped || netgun.kills === 0, 'kills=' + netgun.kills);
check('un predateur est empetre, pas capture',
  netgun.skipped || netgun.bigAlive === null || (netgun.bigAlive === true && netgun.bigStunned === true),
  'vivant=' + netgun.bigAlive + ' etourdi=' + netgun.bigStunned);

// ---------------------------------------------------------------------------
// 5c. Surfacing on an empty tank refills it
// ---------------------------------------------------------------------------

const surfaceAir = await run(`
  const p=g.diver.position;
  // Empty the tank in open water, then swim straight up.
  g.diver.teleport(p.set(g.sub.anchor.x+30, -18, g.sub.anchor.z+30));
  g.diver.oxygen=0;
  // Measure the drowning itself, not the health bar: the shark bite of step 5
  // already pushed it under 100, so "health < 100" would pass here even with
  // drowning switched off. Count only the damage the diver reports as 'drown',
  // over a slice of game time, so neither the bite nor the framerate can fake
  // the result.
  let drownDamage=0;
  const prevHurt=g.diver.hooks.onHurt;
  g.diver.hooks.onHurt=(kind,amount,angle)=>{
    if(kind==="drown") drownDamage+=amount;
    if(prevHurt) prevHurt(kind,amount,angle);
  };
  const hp0=g.diver.health, dt0=g.game.time;
  const measured=await T.until(()=>g.game.time - dt0 > 0.3, 180);
  const drownWindow=g.game.time - dt0;
  g.diver.hooks.onHurt=prevHurt;
  const drownRate=drownDamage / Math.max(0.001, drownWindow);
  const drowning=measured && drownDamage > 0;
  const drownLost=+(hp0 - g.diver.health).toFixed(1);
  // Hold the diver at the waterline the way swimming up would.
  const rose=await T.until(()=>{ p.y = -0.05; return g.diver.oxygen > 10; }, 90);
  const atSurface=g.diver.atSurface;
  // Assert the refill RATE, not an absolute target: the tank fills on game
  // time, and this renderer advances roughly a hundredth of a second of it per
  // real second, so any fixed goal would only measure the framerate.
  const t0=g.game.time, o0=g.diver.oxygen;
  await T.until(()=>{ p.y = -0.05; return g.game.time - t0 > 0.4; }, 150);
  const rate=(g.diver.oxygen - o0) / Math.max(0.001, g.game.time - t0);
  return JSON.stringify({drowning, rose, atSurface,
    drownDamage:+drownDamage.toFixed(1), drownRate:Math.round(drownRate),
    drownWindow:+drownWindow.toFixed(2), drownLost, measured,
    rate:Math.round(rate), oxygen:Math.round(g.diver.oxygen)});
`);
check('la bouteille vide fait des degats',
  surfaceAir.drowning === true && surfaceAir.drownRate >= 4,
  surfaceAir.drownDamage + ' pv de noyade en ' + surfaceAir.drownWindow
    + ' s de jeu, soit ' + surfaceAir.drownRate + ' pv/s (barre de vie: -'
    + surfaceAir.drownLost + ')');
check('la tete au ras de l eau permet de respirer', surfaceAir.atSurface === true);
check('remonter a sec recharge la bouteille', surfaceAir.rose === true);
check('la bouteille se remplit vite en surface',
  surfaceAir.rate >= 40,
  surfaceAir.rate + ' unites par seconde de jeu, soit un plein en '
    + (Math.round((140 / Math.max(1, surfaceAir.rate)) * 10) / 10) + ' s');

// ---------------------------------------------------------------------------
// 6. Death and respawn
// ---------------------------------------------------------------------------

const death = await run(`
  const cargoBefore=g.sub.cargo.length;
  g.diver.applyDamage(999, null, "test");
  const dead=await T.until(()=>T.visible("dead") && g.game.state==="dead", 60);
  document.getElementById("btn-respawn").click();
  const revived=await T.until(()=>g.game.state==="play" && g.diver.alive, 60);
  return JSON.stringify({dead, revived, health:Math.round(g.diver.health),
    oxygen:Math.round(g.diver.oxygen), net:g.diver.net.length,
    cargo:g.sub.cargo.length, cargoBefore});
`);
check('ecran de mort affiche', death.dead === true);
check('reapparition au sous-marin', death.revived === true);
check('vitals restaures', death.health >= 99 && death.oxygen >= 99,
  'pv=' + death.health + ' o2=' + death.oxygen);
check('filet perdu a la mort', death.net === 0);
check('soute conservee a la mort', death.cargo === death.cargoBefore);

// ---------------------------------------------------------------------------
// 7. Codex, pause and help screens
// ---------------------------------------------------------------------------

const screens = await run(`
  await T.key("Tab");
  const codex=await T.until(()=>T.visible("codex"), 60);
  const cards=document.querySelectorAll("#codex-grid > *").length;
  const count=document.getElementById("codex-count").textContent;
  // Two Escapes in a row: the first closes the codex, the second opens the
  // pause menu. They must not land in the same frame, because the input layer
  // keeps the presses in a Set that it empties once per frame, so a second
  // press before the loop has run would simply be swallowed. Waiting for the
  // codex to be gone is what guarantees a frame ran in between.
  await T.key("Escape");
  const closed=await T.until(()=>!T.visible("codex") && g.game.state==="play", 60);
  await T.key("Escape");
  const paused=await T.until(()=>T.visible("pause"), 60);
  document.getElementById("btn-pause-help").click();
  const help=await T.until(()=>T.visible("help"), 60);
  document.querySelector("#help [data-close]").click();
  const backToPause=await T.until(()=>!T.visible("help") && T.visible("pause"), 60);
  document.getElementById("btn-resume").click();
  const resumed=await T.until(()=>g.game.state==="play", 60);
  return JSON.stringify({codex, cards, count, closed, paused, help, backToPause, resumed});
`);
check('carnet ouvert avec Tab', screens.codex === true);
check('une carte par espece', screens.cards === 16, 'cartes=' + screens.cards);
check('compteur du carnet', /\d+\s*\/\s*16/.test(screens.count), screens.count);
check('pause accessible', screens.paused === true);
check('ecran des commandes', screens.help === true);
check('reprise apres la pause', screens.resumed === true,
  'carnet ferme=' + screens.closed + ' retour a la pause=' + screens.backToPause);
await screenshot('carnet');

// ---------------------------------------------------------------------------
// 8. The ten species milestone pays its bonus
// ---------------------------------------------------------------------------

const milestone = await run(`
  // Everything computePrompt() looks at, so a failure here says which of the
  // three guards (state, distance to the sub, walking near the scientist) shut
  // the prompt down instead of just reporting an empty string.
  const diag=()=>({
    state:g.game.state,
    screen:(typeof g.hud.currentScreen==="function"?g.hud.currentScreen():g.hud.currentScreen),
    alive:g.diver.alive, mode:g.diver.mode, sub:g.sub.state,
    subDist:+g.sub.distanceTo(g.diver.position).toFixed(1),
    sciDist:+Math.hypot(g.world.points.scientist.x-g.diver.position.x,
                        g.world.points.scientist.z-g.diver.position.z).toFixed(1),
    cargo:g.sub.cargo.length, net:g.diver.net.length, prompt:T.prompt(),
  });
  const save=g.game.save;
  const known=new Set(Object.keys(save.discovered));
  const fresh=g.species.filter(id=>!known.has(id)).slice(0,10);
  if(fresh.length<10) return JSON.stringify({skipped:true, pool:fresh.length});
  const before=save.medals;
  const start=diag();
  if(g.sub.state!=="deep") return JSON.stringify({skipped:false, error:"le sous-marin n est pas au recif", start});

  // Load the hold, then genuinely ride the sub up the way step 2 does. Forcing
  // sub.state="surface" instead would leave the hull moored on the reef with
  // only its Y following the pier (see the idle branch of sub.js), and would
  // leave the diver wherever the previous steps dropped him: the mount would
  // then depend on five steps of accumulated state rather than on the game.
  for(const id of fresh) g.sub.cargo.push({speciesId:id, name:id, value:10});
  g.diver.net.length=0;
  g.diver.teleport(g.diver.position.copy(g.sub.dockPoint));
  const ready=await T.until(()=>/Remonter/.test(T.prompt()), 90);
  if(!ready) return JSON.stringify({skipped:false, error:"pas d invite de remontee", start, at:diag()});
  await T.key("KeyE");
  const started=await T.until(()=>g.game.state==="transit"||g.sub.state==="ascending", 90);
  // Same fast forward as step 2: the trip runs on game time and this renderer
  // would take several real minutes for a 3.4 s ride.
  await T.until(()=>{ if(g.sub.state==="ascending") g.sub.transitT=0.99; return g.sub.state==="surface"; }, 150);
  const landed=await T.until(()=>g.diver.mode==="walk" && g.game.state==="play", 90);
  const onIsland=diag();

  const sci=g.world.points.scientist; const p=g.diver.position;
  g.diver.teleport(p.set(sci.x+2.5, g.world.heightAt(sci.x+2.5, sci.z+2.5)+0.9, sci.z+2.5));
  const prompted=await T.until(()=>/Presenter/.test(T.prompt()), 90);
  const prompt=T.prompt();
  await T.key("KeyE");
  const opened=await T.until(()=>T.visible("scientist"), 90);
  return JSON.stringify({skipped:false, gained:save.medals-before,
    total:Object.keys(save.discovered).length, bonus:save.expeditionBonusClaimed,
    ready, started, landed, prompted, opened, prompt,
    start, onIsland, at:diag()});
`);
check('palier des dix especes',
  milestone.skipped || (milestone.total >= 10 && milestone.bonus === true && milestone.gained >= 12),
  milestone.skipped
    ? 'especes inedites disponibles=' + milestone.pool
    : milestone.error
      ? milestone.error + ' ' + JSON.stringify(milestone.at || milestone.start)
      : 'catalogue=' + milestone.total + ' medailles gagnees=' + milestone.gained
        + ' bonus=' + milestone.bonus + ' invite=' + JSON.stringify(milestone.prompt)
        + ' ' + JSON.stringify(milestone.at));
await screenshot('palier');

finish();
