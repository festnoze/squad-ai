# AIGUILLAGE - contrats de modules

Signatures publiques reellement livrees. Regles globales : zero build, zero
asset binaire, `three` r169 vendorise, francais sans accents dans le 3D,
jamais de tiret cadratin, pas de `Math.random` dans la simulation.

## src/textures.js
```
createTextures(renderer|null) -> Textures
Textures = { ballast, ground, sleeper, panel, windows, glow, spark, barrier, dispose() }
```
`renderer` sert uniquement a lire l'anisotropie max ; peut etre `null` lors
d'une premiere passe (les textures sont reconstruites une fois le renderer pret).

## src/spline.js  (depend de `three`)
```
createSpline(points:[{x,y,z}]) -> Spline
spline.length
spline.at(s, out:{pos,tangent}) -> out         // zero allocation, lerp entre echantillons precalcules
spline.samplePoints(n) -> THREE.Vector3[]      // tableau frais, pour construire de la geometrie
spline.makeFrame() -> {pos:Vector3, tangent:Vector3}
spline.dispose()
```

## src/network.js  (aucune dependance, pas de `three`)
```
createNetwork(levelDef:{nodes,segments,switches}) -> Network
Network.nodes     Map<id, {id, kind:'spawn'|'exit'|'switch'|'siding', x, z, color}>
Network.segments  Map<id, {id, a, b, length, points, crossing:{sAt,offset,closedFor,period}|null}>
Network.switches  Map<id, {id, nodeId, trunk, branches:[segA,segB], state:0|1}>
network.toggleSwitch(id)          // TOUJOURS bascule, jamais refuse
network.setSwitchState(id, state)
network.switchState(id) -> 0|1
network.isCrossingClosed(segmentId, simTime) -> bool
network.crossingChangesIn(segmentId, simTime) -> number|null
network.resolveArrival(segmentId, dir) -> {kind:'exit',color} | {kind:'siding'}
                                         | {kind:'through',segmentId,dir,sAbs} | {kind:'blocked'}
network.otherEnd(segmentId, nodeId) -> nodeId
network.dispose()
```

## src/trains.js  (pure, **aucun** `import * as THREE`)
Position d'un train : `(segmentId, dir:+1|-1, sAbs)`, `sAbs` = abscisse
absolue depuis le noeud `a` du segment. La resolution d'un aiguillage est
relue a chaque tick et n'est appliquee que le tick ou le train atteint
reellement le bout du segment : c'est ce qui rend "la position au moment du
franchissement decide la route" vrai sans etat supplementaire.
```
createTrainSim(network, opts?) -> Sim
Sim.trains   // array vivante de {id,color,segmentId,dir,sAbs,speed,state,coupledSecondColor}
             // state: 'running'|'queued'|'parked'|'delivered'|'crashed'
Sim.events   // {delivered:[{id,color}], wrongExit:[{id,color,expected}], crashed:null|{ids,segmentId,sAbs}}
Sim.params   // constantes effectives (cruiseSpeed, safetyGap, crashGap, coupleGap, ...)
sim.time                       // secondes simulees (avance meme pendant la pause tactique)
sim.spawnTrain({nodeId,color,secondColor?}) -> trainId|null
sim.reverseTrain(trainId) -> bool     // seulement si le train est 'parked'
sim.step(dt, paused:bool)             // paused gele le mouvement des trains, pas sim.time
sim.clearEvents()
sim.livingCount() -> number            // ni 'delivered' ni 'crashed'
sim.dispose()
```
Un train double porte `coupledSecondColor` jusqu'a ce que son avant atteigne
le premier noeud rencontre : a cet instant il devient un train simple sur sa
route, et un nouveau train independant est cree a `sAbs - dir*coupleGap`.

## src/schedule.js  (pure)
```
createScheduler(spawnList:[{t,nodeId,color,secondColor?}]) -> Scheduler
scheduler.pending(simTime) -> due[]   // consomme et retourne les entrees echues
scheduler.done / scheduler.remaining / scheduler.reset()
```

## src/levels.js  (pure, aucune dependance a `three`)
```
COLORS = { RED, BLUE, YELLOW, GREEN }
LEVELS: LevelDef[12]   // index, id, name, teach, pauseBudget, graceSeconds,
                       // network:{nodes,segments,switches}, spawns, trainCount
levelCount() -> number
getLevel(index) -> LevelDef
```

## src/camera.js  (depend de `three`)
```
createCameraRig(aspect) -> rig
rig.camera
rig.frame(bounds:{minX,maxX,minZ,maxZ})
rig.orbit(dx, dy)              // souris / trackpad
rig.orbitRate(yawRate, pitchRate, dt)   // clavier IJKL
rig.zoom(deltaPixels)
rig.update(dt)
rig.resize(aspect)
```

## src/input.js  (depend de `three`? non - DOM pur)
```
createInput(canvas) -> input
input.onOrbit(cb(dx,dy)) / input.onZoom(cb(delta)) / input.onPick(cb(ndcX,ndcY))
input.onCommand(cb(name))   // 'pause' | 'mute' | 'restart' | 'pause-tactical'
input.pollKeyboardOrbit(dt, orbitRateFn)
input.setEnabled(bool)
input.dispose()
```
Un clic gauche qui bouge peu (< 6px) est un "pick" ; au dela, ou avec le
bouton du milieu, c'est une orbite. Le glissement lateral dominant d'une
molette de trackpad oriente la camera au lieu de zoomer.

## src/hud.js  (DOM pur, aucune logique de jeu)
```
createHUD() -> hud
hud.show()/hide()/showScreen(name)/hideAllScreens()
hud.setLoading(progress01, line) / hud.setLevelInfo(name) / hud.setTrainCount(d,t)
hud.setClock(seconds) / hud.setTeach(text|null) / hud.setPauseBudget(remaining,total)
hud.setTacticalActive(bool) / hud.setMuted(bool) / hud.setVolume(v01)
hud.toast(text) / hud.banner(title, sub, ms)
hud.setLevelGrid(levels, unlockedIndex, bestScores[]) / hud.setLevelDetail(level, best)
hud.setResults({success,subtitle,delivered,total,late,stars,hasNext})
```

## src/audio.js  (Web Audio pur)
```
createAudio() -> audio
audio.resume() / audio.setMasterVolume(v01) / audio.toggleMute() -> bool
audio.switchClick(state) / audio.whistle() / audio.chime(good) / audio.bellTick()
audio.setBell(active) / audio.setAlarm(active) / audio.crash() / audio.finish(won)
audio.update(dt) / audio.dispose()
```

## src/replay.js
```
createReplay() -> replay
replay.start(worldPos)
replay.update(dtRealSeconds, cameraRig) -> bool   // true tant que la sequence tourne
replay.active
replay.dispose()
```

## src/render/scene.js  (depend de `three`)
```
createSceneRig(canvas, textures) -> { renderer, scene, moon, resize(w,h), render(camera), dispose() }
```

## src/render/track.js  (depend de `three`, `../spline.js`)
```
createTrackRender(network, textures) -> trackRender
trackRender.group
trackRender.getSpline(segmentId) -> Spline
trackRender.nodeWorldPos(nodeId) -> Vector3
trackRender.switchPickables   // [{switchId, mesh, pos}]
trackRender.sidingPickables   // [{nodeId, mesh, pos}]
trackRender.update(dt, simTime)
trackRender.dispose()
```

## src/render/trains.js  (depend de `three`)
```
createTrainRender(textures) -> trainRender
trainRender.group
trainRender.sync(simTrains, trackRender, coupleGap)
trainRender.dispose()
```

## src/main.js
Assemble tout, machine a etats `loading -> menu -> levels -> playing ->
(paused | replay | results)`. Expose `window.game` (debug) et
`window.__ready = true` une fois le menu affiche.

## Non negociable
- Demarre sans erreur console, 60 fps visé sur GPU integre.
- Aucun `TODO`, aucun placeholder, aucune fonction vide.
- Un module n'importe jamais un symbole non liste ici.
