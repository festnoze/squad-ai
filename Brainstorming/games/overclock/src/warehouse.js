/**
 * OVERCLOCK - warehouse model.
 *
 * Pure data and rules, no three.js, no DOM. Every mutation goes through one of
 * the action methods, and every action returns the same shaped result so the
 * renderer and the HUD can react without knowing which action ran.
 */

/** dir 0 = +x, 1 = +z, 2 = -x, 3 = -z. Turning right is dir + 1. */
export const DIRS = [
  { x: 1, z: 0 },
  { x: 0, z: 1 },
  { x: -1, z: 0 },
  { x: 0, z: -1 },
];

export const COLOR_NONE = 'n';

const MARKERS = {
  '.': { target: false, crate: false, color: COLOR_NONE },
  '*': { target: true, crate: false, color: COLOR_NONE },
  C: { target: false, crate: true, color: COLOR_NONE },
  r: { target: false, crate: false, color: 'r' },
  g: { target: false, crate: false, color: 'g' },
  b: { target: false, crate: false, color: 'b' },
  R: { target: true, crate: false, color: 'r' },
  G: { target: true, crate: false, color: 'g' },
  B: { target: true, crate: false, color: 'b' },
};

function ok(reason, extra) {
  const res = { ok: true, reason: reason || '', moved: false };
  if (extra) Object.assign(res, extra);
  return res;
}

function ko(reason) {
  return { ok: false, reason, moved: false };
}

export function createWarehouse(level) {
  const rows = level.h.length;
  const cols = level.h[0].length;
  const tiles = new Array(cols * rows);

  const wh = {
    level,
    cols,
    rows,
    tiles,
    drone: { x: 0, z: 0, dir: 0, level: 0, carrying: false },
    targets: 0,
    lit: 0,

    index(x, z) {
      return z * cols + x;
    },

    at(x, z) {
      if (x < 0 || z < 0 || x >= cols || z >= rows) return null;
      return tiles[z * cols + x];
    },

    /** Walkable surface height of a tile, or null when there is nothing to stand on. */
    topOf(tile) {
      if (!tile) return null;
      if (tile.h < 0 && !tile.crate) return null;
      return tile.h + (tile.crate ? 1 : 0);
    },

    tileUnderDrone() {
      return wh.at(wh.drone.x, wh.drone.z);
    },

    aheadTile(steps) {
      const d = DIRS[wh.drone.dir];
      return wh.at(wh.drone.x + d.x * (steps || 1), wh.drone.z + d.z * (steps || 1));
    },

    reset() {
      for (let z = 0; z < rows; z++) {
        const hrow = level.h[z];
        const mrow = level.m[z];
        for (let x = 0; x < cols; x++) {
          const hc = hrow[x];
          const mc = MARKERS[mrow[x]] ? mrow[x] : '.';
          const mk = MARKERS[mc];
          const tile = tiles[z * cols + x] || (tiles[z * cols + x] = { x: 0, z: 0, h: 0, color: COLOR_NONE, target: false, lit: false, crate: false });
          tile.x = x;
          tile.z = z;
          tile.h = hc === '.' ? -1 : hc.charCodeAt(0) - 48;
          tile.color = mk.color;
          tile.target = mk.target;
          tile.crate = mk.crate;
          tile.lit = false;
        }
      }
      wh.targets = 0;
      wh.lit = 0;
      for (let i = 0; i < tiles.length; i++) if (tiles[i].target) wh.targets++;
      wh.drone.x = level.start.x;
      wh.drone.z = level.start.z;
      wh.drone.dir = level.start.dir;
      wh.drone.carrying = false;
      wh.drone.level = wh.topOf(wh.tileUnderDrone()) || 0;
      return wh;
    },

    solved() {
      return wh.targets > 0 && wh.lit >= wh.targets;
    },

    /** Colour of the tile the drone stands on, used by instruction conditions. */
    colorUnder() {
      const t = wh.tileUnderDrone();
      return t ? t.color : COLOR_NONE;
    },

    turn(delta) {
      wh.drone.dir = (wh.drone.dir + delta + 4) % 4;
      return ok('', { turned: delta });
    },

    forward() {
      const t = wh.aheadTile(1);
      if (!t) return ko('BORD DE ZONE');
      const top = wh.topOf(t);
      if (top === null) return ko('VIDE DEVANT');
      if (top !== wh.drone.level) return ko(top > wh.drone.level ? 'MARCHE TROP HAUTE' : 'DENIVELE, UTILISER SAUT');
      wh.drone.x = t.x;
      wh.drone.z = t.z;
      return ok('', { moved: true, to: t, top });
    },

    /** One step up, any drop down, or across a single void cell. */
    jump() {
      const near = wh.aheadTile(1);
      if (!near) return ko('BORD DE ZONE');
      const nearTop = wh.topOf(near);
      if (nearTop === null) {
        const far = wh.aheadTile(2);
        const farTop = wh.topOf(far);
        if (farTop === null) return ko('VIDE TROP LARGE');
        if (farTop !== wh.drone.level) return ko('RECEPTION A MAUVAISE HAUTEUR');
        wh.drone.x = far.x;
        wh.drone.z = far.z;
        wh.drone.level = farTop;
        return ok('', { moved: true, to: far, top: farTop, gap: true });
      }
      if (nearTop === wh.drone.level) return ko('MEME HAUTEUR, UTILISER AVANCER');
      if (nearTop > wh.drone.level + 1) return ko('MARCHE TROP HAUTE');
      wh.drone.x = near.x;
      wh.drone.z = near.z;
      const climbed = nearTop - wh.drone.level;
      wh.drone.level = nearTop;
      return ok('', { moved: true, to: near, top: nearTop, climb: climbed });
    },

    activate() {
      const t = wh.tileUnderDrone();
      if (!t || !t.target) return ko('PAS DE CIBLE ICI');
      if (t.lit) return ok('DEJA ALLUMEE', { tile: t, again: true });
      t.lit = true;
      wh.lit++;
      return ok('', { tile: t, litNow: true });
    },

    paint(color) {
      const t = wh.tileUnderDrone();
      if (!t) return ko('AUCUNE DALLE');
      if (t.color === color) return ok('DEJA DE CETTE COULEUR', { tile: t, again: true });
      t.color = color;
      return ok('', { tile: t, painted: color });
    },

    grab() {
      if (wh.drone.carrying) return ko('DEJA UNE CAISSE');
      const t = wh.aheadTile(1);
      if (!t) return ko('BORD DE ZONE');
      if (!t.crate) return ko('RIEN A PRENDRE');
      if (t.h !== wh.drone.level) return ko('CAISSE HORS DE PORTEE');
      t.crate = false;
      wh.drone.carrying = true;
      return ok('', { tile: t, took: true });
    },

    drop() {
      if (!wh.drone.carrying) return ko('AUCUNE CAISSE EN MAIN');
      const t = wh.aheadTile(1);
      if (!t) return ko('BORD DE ZONE');
      if (t.crate) return ko('PLACE OCCUPEE');
      if (t.h !== wh.drone.level && t.h !== wh.drone.level - 1) return ko('HORS DE PORTEE');
      t.crate = true;
      wh.drone.carrying = false;
      return ok('', { tile: t, placed: true });
    },
  };

  return wh.reset();
}
