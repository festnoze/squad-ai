// Logique de decouverte et condition de victoire.
//
// Coeur de la boucle de jeu : trois elements a valider (ocean liquide,
// vegetation, faune) sur une MEME planete. Chaque element se valide apres
// GAME.SCAN_TIME secondes de proximite CONTINUE. Le compteur se vide a la
// moitie de la vitesse de remplissage quand la condition est perdue, ce qui
// pardonne les allers-retours et les micro-decrochages.
//
// Ce module est du pur etat de jeu : aucune dependance a three, aucune au DOM.
// Il ne connait ni viewOrigin ni espace vue. Les positions qu'il memorise sont
// celles qu'on lui donne, donc en ESPACE LOCAL PLANETE, recopiees en objets
// simples { x, y, z } pour ne retenir aucune reference a un vecteur reutilise
// par un autre module.
//
// Canal des statistiques de partie (choix documente) : main.js pousse son objet
// de stats dans `ctx.stats` a chaque frame (aucune plomberie supplementaire).
// `setStats(stats)` existe comme alternative imperative pour un appelant qui
// prefere le fournir une seule fois ; le dernier ecrit gagne. Champs lus :
// `elapsed`, `planetsVisited`, `distanceTravelled` (alias `distance`). Chaque
// champ absent est remplace par une valeur calculee ici.

import { Emitter } from '../core/events.js';
import { GAME } from '../core/settings.js';
import { formatDistance } from '../core/math.js';

const KEYS = ['ocean', 'trees', 'fauna'];

// Reglages de scan.
const SCAN_BOOST = 2.5; // multiplicateur d'un appui sur la touche de scan
const SCAN_BOOST_TIME = 0.6; // duree de ce coup de pouce, en secondes
const DECAY_RATIO = 0.5; // vidage = moitie de la vitesse de remplissage
const MAX_STEP = 0.25; // dt borne : un onglet en arriere-plan ne valide rien

// Reglages des indices.
const IDLE_HINT_DELAY = 6; // secondes sur une planete sans progression
const HINT_COOLDOWN = 12; // au plus un indice automatique toutes les 12 s
const MANUAL_HINT_COOLDOWN = 1.2; // anti-spam de l'indice demande par le joueur
const DESCEND_HINT_ALTITUDE = GAME.OCEAN_SCAN_ALTITUDE * 1.35;

// Altitude sous laquelle on considere que le joueur est "entre en atmosphere",
// utilisee seulement si la planete n'a pas d'enveloppe declaree.
const VISIT_RADIUS_FRACTION = 0.12;

// Libelles par defaut. Toute cle presente dans `strings` a la priorite, ce qui
// permet a game/strings.js de tout retraduire sans toucher a ce fichier.
const FALLBACK = {
  labelOcean: 'Ocean liquide',
  labelTrees: 'Vegetation',
  labelFauna: 'Faune',

  hintSpace: 'Choisis un monde dans le panneau de navigation et descends dans son atmosphère.',
  hintDescend: 'Trop haut pour analyser : descends vers la surface (altitude {alt}).',
  hintOceanAltitude: 'Eau liquide détectée sous le vaisseau : descends sous {range} pour lancer l\'analyse.',
  hintFindWater: 'Aucune étendue d\'eau sous le vaisseau : suis les zones sombres de la minimap.',
  hintTreeFar: 'Signal de biomasse à {dist} : rapproche-toi et reste stable.',
  hintFaunaFar: 'Mouvement organique à {dist} : approche doucement, sans effrayer la nuée.',
  hintNoSignal: 'Aucun signal biologique détecté à portée.',
  hintEquator: 'Les zones vertes se concentrent vers l\'équateur : longe-le à basse altitude.',
  hintHold: 'Le scanner exige {scan} de proximité continue : ralentis et maintiens la distance.',
  hintOtherWorlds: 'Aucun signal biologique détecté à portée. Le système compte d\'autres mondes.',
  hintAlmost: 'Deux relevés sur trois ici : ne quitte pas cette planète sans le troisième.',
};

/** Lecture d'un libelle avec substitution de {tokens}. */
function textOf(strings, key, vars) {
  let raw = null;
  if (typeof strings === 'function') raw = strings(key);
  else if (strings && typeof strings[key] === 'string') raw = strings[key];
  if (typeof raw !== 'string' || raw.length === 0) raw = FALLBACK[key] || key;
  if (!vars) return raw;
  return raw.replace(/\{(\w+)\}/g, (m, name) => (vars[name] !== undefined ? String(vars[name]) : m));
}

/** Recopie defensive d'un point (Vector3 ou objet simple) en objet simple. */
function copyPoint(p) {
  if (!p) return null;
  const x = p.x;
  const y = p.y;
  const z = p.z;
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) return null;
  return { x, y, z };
}

function makeEntry(id, name) {
  return {
    id,
    name,
    done: { ocean: false, trees: false, fauna: false },
    progress: { ocean: 0, trees: 0, fauna: 0 },
    positions: { ocean: null, trees: null, fauna: null },
    at: { ocean: 0, trees: 0, fauna: 0 },
    order: [],
    visited: false,
    timeOnPlanet: 0,
  };
}

/**
 * @param {{ audio?: object, strings?: object|Function }} deps
 */
export function createDiscovery({ audio, strings } = {}) {
  const emitter = new Emitter();

  // Etat par planete. `entries` double la Map pour pouvoir iterer par index
  // sans allouer d'iterateur a chaque frame.
  const byPlanet = new Map();
  const entries = [];
  const visited = new Set();

  // Objets reutilises : update() et progressFor() n'allouent rien.
  const cond = { ocean: false, trees: false, fauna: false };
  const progressOut = { ocean: 0, trees: 0, fauna: 0, scanning: null };
  const scanningOut = { key: null, progress: 0 };

  let stats = null;
  let elapsed = 0; // horloge interne, secours si stats.elapsed est absent
  let boostTimer = 0;
  let hintCooldown = 0;
  let noProgressTimer = 0;
  let currentId = null;
  let activeKey = null;
  let lastHintKey = null;
  let won = false;
  let winReport = null;

  function play(name) {
    if (audio && typeof audio.play === 'function') audio.play(name);
  }

  function label(key) {
    if (key === 'ocean') return textOf(strings, 'labelOcean');
    if (key === 'trees') return textOf(strings, 'labelTrees');
    return textOf(strings, 'labelFauna');
  }

  function entryFor(spec) {
    const id = spec.id;
    let e = byPlanet.get(id);
    if (!e) {
      e = makeEntry(id, spec.name || id);
      byPlanet.set(id, e);
      entries.push(e);
    }
    return e;
  }

  // -------------------------------------------------------------------------
  // Indices contextuels
  // -------------------------------------------------------------------------

  // Tampon de candidats reutilise (les indices sont rares, mais autant eviter
  // toute pression sur le GC).
  const candidateKeys = [];
  const candidateVars = [];

  function pushCandidate(key, vars) {
    candidateKeys.push(key);
    candidateVars.push(vars || null);
  }

  /**
   * Construit la liste des indices pertinents, du plus precis au plus general.
   * Regle d'honnetete : on ne revele JAMAIS qu'une planete est morte. Si rien
   * n'est a portee, on dit exactement cela ("aucun signal biologique detecte a
   * portee"), ce que le joueur pourrait constater lui-meme.
   */
  function buildCandidates(entry, spec, ctx, alt, wide) {
    candidateKeys.length = 0;
    candidateVars.length = 0;

    if (!spec) {
      pushCandidate('hintSpace', null);
      return;
    }

    if (Number.isFinite(alt) && alt > DESCEND_HINT_ALTITUDE) {
      pushCandidate('hintDescend', { alt: formatDistance(alt) });
    }

    const nt = ctx.nearestTree;
    const nf = ctx.nearestFauna;

    if (!entry.done.ocean) {
      if (ctx.overWater && alt >= GAME.OCEAN_SCAN_ALTITUDE) {
        pushCandidate('hintOceanAltitude', { range: formatDistance(GAME.OCEAN_SCAN_ALTITUDE) });
      } else if (!ctx.overWater && alt <= DESCEND_HINT_ALTITUDE) {
        pushCandidate('hintFindWater', null);
      }
    }
    if (!entry.done.trees && nt && Number.isFinite(nt.distance)) {
      pushCandidate('hintTreeFar', { dist: formatDistance(nt.distance) });
    }
    if (!entry.done.fauna && nf && Number.isFinite(nf.distance)) {
      pushCandidate('hintFaunaFar', { dist: formatDistance(nf.distance) });
    }

    const foundHere = entry.order.length;
    if (foundHere === 2) pushCandidate('hintAlmost', null);

    if (wide) {
      if (!entry.done.trees || !entry.done.fauna) pushCandidate('hintEquator', null);
      pushCandidate('hintHold', { scan: `${GAME.SCAN_TIME.toFixed(1)} s` });
    }

    if (candidateKeys.length === 0) {
      // Rien de precis a dire : on reste factuel.
      pushCandidate(entry.timeOnPlanet > IDLE_HINT_DELAY * 4 ? 'hintOtherWorlds' : 'hintNoSignal', null);
    }
  }

  function emitHint(entry, spec, ctx, alt, wide, cooldown) {
    buildCandidates(entry, spec, ctx, alt, wide);
    let pick = 0;
    if (candidateKeys.length > 1 && candidateKeys[0] === lastHintKey) pick = 1;
    const key = candidateKeys[pick];
    const text = textOf(strings, key, candidateVars[pick]);
    lastHintKey = key;
    hintCooldown = cooldown;

    // Le payload se comporte comme un objet ET comme une chaine : un appelant
    // peut faire hud.setHint(e.text) ou hud.setHint(String(e)) sans se tromper.
    const payload = {
      key,
      text,
      planetId: spec ? spec.id : null,
      toString() {
        return this.text;
      },
    };
    emitter.emit('hint', payload);
    return payload;
  }

  // -------------------------------------------------------------------------
  // Validation et victoire
  // -------------------------------------------------------------------------

  function validate(entry, spec, key, ctx) {
    entry.progress[key] = 1;
    entry.done[key] = true;
    entry.at[key] = elapsedNow();
    entry.order.push(key);

    let position = null;
    if (key === 'ocean') {
      // main.js peut fournir la position locale du vaisseau (champ optionnel,
      // cf. divergences documentees). Sans elle, pas de marqueur : le HUD sait
      // gerer un marqueur absent.
      position = copyPoint(ctx.playerLocal || ctx.cameraLocal || ctx.shipLocal || null);
    } else if (key === 'trees') {
      position = copyPoint(ctx.nearestTree && ctx.nearestTree.position);
    } else {
      position = copyPoint(ctx.nearestFauna && ctx.nearestFauna.position);
    }
    entry.positions[key] = position;

    play('found');
    emitter.emit('discover', {
      planetId: entry.id,
      planetName: entry.name,
      key,
      label: label(key),
      position,
      at: entry.at[key],
      remaining: 3 - entry.order.length,
    });

    if (entry.done.ocean && entry.done.trees && entry.done.fauna && !won) triggerWin(entry, spec);
  }

  function elapsedNow() {
    if (stats && Number.isFinite(stats.elapsed)) return stats.elapsed;
    return elapsed;
  }

  function triggerWin(entry, spec) {
    won = true;
    const discoveries = [];
    for (let i = 0; i < entry.order.length; i++) {
      const key = entry.order[i];
      discoveries.push({
        key,
        label: label(key),
        planetId: entry.id,
        planetName: entry.name,
        position: entry.positions[key],
        at: entry.at[key],
      });
    }
    let travelled = 0;
    if (stats) {
      if (Number.isFinite(stats.distanceTravelled)) travelled = stats.distanceTravelled;
      else if (Number.isFinite(stats.distance)) travelled = stats.distance;
    }
    winReport = {
      planetId: entry.id,
      planetName: entry.name,
      planetType: spec ? spec.typeLabel || spec.type : null,
      elapsed: elapsedNow(),
      planetsVisited:
        stats && Number.isFinite(stats.planetsVisited) ? stats.planetsVisited : visited.size,
      distanceTravelled: travelled,
      discoveries,
    };
    play('win');
    emitter.emit('win', winReport);
  }

  // -------------------------------------------------------------------------
  // Boucle
  // -------------------------------------------------------------------------

  function update(dt, ctx) {
    let step = Number.isFinite(dt) ? dt : NaN;
    if (!Number.isFinite(step) && ctx) {
      step = Number.isFinite(ctx.dt) ? ctx.dt : Number.isFinite(ctx.dtScaled) ? ctx.dtScaled : 0;
    }
    if (!Number.isFinite(step) || step < 0) step = 0;
    if (step > MAX_STEP) step = MAX_STEP;

    elapsed += step;
    if (hintCooldown > 0) hintCooldown = Math.max(0, hintCooldown - step);
    if (!ctx) return;
    if (ctx.stats) stats = ctx.stats;

    // La planete peut arriver sous forme d'objet Planet (avec .spec) ou de spec
    // brut : on accepte les deux.
    const planet = ctx.planet || null;
    const spec = planet ? planet.spec || planet : null;
    const id = spec && spec.id ? spec.id : null;
    const entry = spec && id ? entryFor(spec) : null;

    if (id !== currentId) {
      currentId = id;
      noProgressTimer = 0;
      activeKey = null;
      boostTimer = 0;
      if (entry) entry.timeOnPlanet = 0;
    }

    const alt = Number.isFinite(ctx.altitude) ? ctx.altitude : Infinity;

    if (entry) {
      entry.timeOnPlanet += step;
      // Entree en atmosphere : c'est ce qui compte comme "planete visitee".
      if (!entry.visited) {
        const shell = spec.atmosphere && Number.isFinite(spec.atmosphere.height)
          ? spec.atmosphere.height
          : spec.radius * VISIT_RADIUS_FRACTION;
        if (alt < shell) {
          entry.visited = true;
          visited.add(id);
          emitter.emit('visit', { planetId: id, planetName: entry.name, count: visited.size });
        }
      }
    }

    // Conditions de proximite du moment.
    cond.ocean = !!(spec && spec.hasOcean && ctx.overWater && alt < GAME.OCEAN_SCAN_ALTITUDE);
    const nt = ctx.nearestTree;
    const nf = ctx.nearestFauna;
    cond.trees = !!(
      spec &&
      spec.hasTrees &&
      nt &&
      Number.isFinite(nt.distance) &&
      nt.distance < GAME.TREE_SCAN_RANGE
    );
    cond.fauna = !!(
      spec &&
      spec.hasFauna &&
      nf &&
      Number.isFinite(nf.distance) &&
      nf.distance < GAME.FAUNA_SCAN_RANGE
    );

    // Un seul scan progresse a la fois : on prend la condition non validee la
    // plus avancee (stabilite), les egalites tranchees par l'ordre
    // ocean > trees > fauna.
    activeKey = null;
    if (entry && !won) {
      let best = -1;
      for (let i = 0; i < KEYS.length; i++) {
        const key = KEYS[i];
        if (!cond[key] || entry.done[key]) continue;
        const p = entry.progress[key];
        if (p > best) {
          best = p;
          activeKey = key;
        }
      }
    }

    // Appui sur scan : accelere le scan en cours, sinon explique ce qui manque.
    if (ctx.scanPressed) {
      play('scan');
      if (activeKey) {
        boostTimer = SCAN_BOOST_TIME;
      } else if (hintCooldown <= 0) {
        // Indice demande : reponse immediate, avec un simple anti-spam.
        emitHint(
          entry || makeEntry(id || 'void', spec ? spec.name : ''),
          spec,
          ctx,
          alt,
          false,
          MANUAL_HINT_COOLDOWN,
        );
      }
    }

    // Vidage progressif de tout ce qui ne progresse pas, sur toutes les
    // planetes (une progression laissee derriere soi retombe elle aussi).
    const fillRate = 1 / GAME.SCAN_TIME;
    const decay = fillRate * DECAY_RATIO * step;
    if (decay > 0) {
      for (let i = 0; i < entries.length; i++) {
        const e = entries[i];
        for (let k = 0; k < KEYS.length; k++) {
          const key = KEYS[k];
          if (e.done[key]) continue;
          if (e === entry && key === activeKey) continue;
          if (e.progress[key] > 0) e.progress[key] = Math.max(0, e.progress[key] - decay);
        }
      }
    }

    let progressed = false;
    if (activeKey && step > 0) {
      const mult = boostTimer > 0 ? SCAN_BOOST : 1;
      const gain = fillRate * mult * step;
      if (gain > 0) {
        entry.progress[activeKey] = Math.min(1, entry.progress[activeKey] + gain);
        progressed = true;
        if (entry.progress[activeKey] >= 1) {
          const key = activeKey;
          activeKey = null;
          boostTimer = 0;
          validate(entry, spec, key, ctx);
        }
      }
    }
    if (boostTimer > 0) boostTimer = Math.max(0, boostTimer - step);

    // Indice automatique : sur la planete depuis plus de 6 s sans progression.
    if (progressed) noProgressTimer = 0;
    else noProgressTimer += step;
    if (
      !won &&
      entry &&
      entry.timeOnPlanet > IDLE_HINT_DELAY &&
      noProgressTimer > IDLE_HINT_DELAY &&
      hintCooldown <= 0
    ) {
      emitHint(entry, spec, ctx, alt, true, HINT_COOLDOWN);
      noProgressTimer = 0;
    }
  }

  /**
   * Etat d'avancement d'une planete. L'objet retourne est REUTILISE d'un appel
   * a l'autre (le HUD l'interroge chaque frame) : lis-le, ne le stocke pas.
   */
  function progressFor(planetId) {
    const id = planetId === undefined || planetId === null ? currentId : planetId;
    const e = id ? byPlanet.get(id) : null;
    if (!e) {
      progressOut.ocean = 0;
      progressOut.trees = 0;
      progressOut.fauna = 0;
      progressOut.scanning = null;
      return progressOut;
    }
    progressOut.ocean = e.done.ocean ? 1 : e.progress.ocean;
    progressOut.trees = e.done.trees ? 1 : e.progress.trees;
    progressOut.fauna = e.done.fauna ? 1 : e.progress.fauna;
    if (activeKey && e.id === currentId) {
      scanningOut.key = activeKey;
      scanningOut.progress = e.progress[activeKey];
      progressOut.scanning = scanningOut;
    } else {
      progressOut.scanning = null;
    }
    return progressOut;
  }

  /** Vrai si les 3 elements sont valides sur cette planete. */
  function isComplete(planetId) {
    const e = byPlanet.get(planetId);
    return !!(e && e.done.ocean && e.done.trees && e.done.fauna);
  }

  /** Marqueurs de minimap : positions locales des decouvertes d'une planete. */
  function markersFor(planetId) {
    const e = byPlanet.get(planetId === undefined || planetId === null ? currentId : planetId);
    const out = [];
    if (!e) return out;
    for (let i = 0; i < KEYS.length; i++) {
      const key = KEYS[i];
      const p = e.positions[key];
      if (e.done[key] && p) out.push({ key, label: label(key), position: p });
    }
    return out;
  }

  function reset() {
    byPlanet.clear();
    entries.length = 0;
    visited.clear();
    stats = null;
    elapsed = 0;
    boostTimer = 0;
    hintCooldown = 0;
    noProgressTimer = 0;
    currentId = null;
    activeKey = null;
    lastHintKey = null;
    won = false;
    winReport = null;
  }

  return {
    update,
    progressFor,
    isComplete,
    markersFor,

    get won() {
      return won;
    },
    get winReport() {
      return winReport;
    },
    get visitedCount() {
      return visited.size;
    },
    /** Identifiants des planetes ou le joueur est entre en atmosphere. */
    getVisited() {
      return Array.from(visited);
    },

    /** Statistiques de partie, alternative a ctx.stats. */
    setStats(next) {
      stats = next || null;
    },

    onDiscover(cb) {
      return emitter.on('discover', cb);
    },
    onWin(cb) {
      return emitter.on('win', cb);
    },
    onHint(cb) {
      return emitter.on('hint', cb);
    },
    onVisit(cb) {
      return emitter.on('visit', cb);
    },

    reset,

    dispose() {
      reset();
      emitter.clear();
    },
  };
}
