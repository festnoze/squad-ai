/**
 * The level, as plain data. Deliberately free of three.js imports so the layout
 * can be loaded and checked by tools/check-level.mjs without a browser or a GPU
 * - that check is what guards the progression gating.
 */
export const TILE = 4;
export const GRID_W = 50;
export const GRID_D = 42;
export const WALL_H = 4.4;
export const HALL_H = 7.0;
export const YARD_H = 9.0;
export const BACK_H = 3.1;   // the backrooms ceiling sits low enough to feel wrong

/** World-space centre of a tile column. */
export function tileX(ix) { return ix * TILE + TILE / 2; }
export function tileZ(iz) { return iz * TILE + TILE / 2; }

/**
 * The prison, as a list of rectangular areas carved out of a solid block.
 * Two areas that share an edge open into each other, so a 1-tile area between
 * two rooms is a doorway. `h` is the ceiling height, `wall`/`floor` name the
 * textures, `dark` dims the ambient fixture density.
 */
export const AREAS = [
  // ------------------------------------------------------- cell wing (west)
  { id: 'corridorA', x0: 1, z0: 7, x1: 20, z1: 8, wall: 'wallCell', floor: 'floor', h: WALL_H, name: 'Coursive A' },
  { id: 'gateA', x0: 21, z0: 7, x1: 21, z1: 8, wall: 'metal', floor: 'floor', h: WALL_H, name: 'Sas A' },
  { id: 'vertLinkE', x0: 20, z0: 9, x1: 21, z1: 14, wall: 'wallCell', floor: 'floor', h: WALL_H, name: 'Coursive B' },

  // -------------------------------------------------------------- the hub
  { id: 'rotunda', x0: 22, z0: 4, x1: 29, z1: 13, wall: 'wall', floor: 'tile', h: HALL_H, name: 'Rotonde centrale' },
  { id: 'northCorr', x0: 30, z0: 4, x1: 45, z1: 5, wall: 'wall', floor: 'floor', h: WALL_H, name: 'Couloir nord' },
  { id: 'gpLink', x0: 33, z0: 6, x1: 34, z1: 6, wall: 'wall', floor: 'tile', h: WALL_H, name: 'Poste de garde' },
  // Stops at x36: column 37 is the wall between the post and solitary.
  { id: 'guardPost', x0: 31, z0: 7, x1: 36, z1: 12, wall: 'wall', floor: 'tile', h: WALL_H, name: 'Poste de garde' },
  { id: 'armLink', x0: 42, z0: 6, x1: 42, z1: 6, wall: 'metal', floor: 'metal', h: WALL_H, name: 'Armurerie' },
  { id: 'armory', x0: 40, z0: 7, x1: 45, z1: 13, wall: 'metal', floor: 'metal', h: WALL_H, name: 'Armurerie' },

  // ------------------------------------------------------ the spine (south)
  { id: 'westCorr', x0: 1, z0: 15, x1: 21, z1: 16, wall: 'wall', floor: 'floor', h: WALL_H, name: 'Couloir principal' },
  { id: 'southCorr', x0: 22, z0: 15, x1: 45, z1: 16, wall: 'wall', floor: 'floor', h: WALL_H, name: 'Couloir principal' },
  { id: 'rotLinkS', x0: 25, z0: 14, x1: 26, z1: 14, wall: 'wall', floor: 'tile', h: HALL_H, name: 'Rotonde centrale' },

  { id: 'laundLink', x0: 6, z0: 17, x1: 7, z1: 17, wall: 'wall', floor: 'floor', h: WALL_H, name: 'Buanderie' },
  { id: 'laundry', x0: 3, z0: 18, x1: 10, z1: 23, wall: 'wall', floor: 'floor', h: WALL_H, name: 'Buanderie' },
  { id: 'utilLink', x0: 16, z0: 17, x1: 16, z1: 17, wall: 'wall', floor: 'floor', h: WALL_H, name: 'Local technique' },
  { id: 'utility', x0: 13, z0: 18, x1: 19, z1: 23, wall: 'wall', floor: 'floor', h: WALL_H, name: 'Local technique' },
  { id: 'showLink', x0: 24, z0: 17, x1: 25, z1: 17, wall: 'wall', floor: 'tile', h: WALL_H, name: 'Douches' },
  { id: 'showers', x0: 22, z0: 18, x1: 28, z1: 24, wall: 'wall', floor: 'tile', h: WALL_H, name: 'Douches' },
  { id: 'cantLink', x0: 36, z0: 17, x1: 37, z1: 17, wall: 'wall', floor: 'tile', h: WALL_H, name: 'Refectoire' },
  { id: 'canteen', x0: 31, z0: 18, x1: 43, z1: 24, wall: 'wall', floor: 'tile', h: HALL_H, name: 'Refectoire' },

  // -------------------------------------------------- the west service wing
  { id: 'westHall', x0: 2, z0: 25, x1: 19, z1: 26, wall: 'wall', floor: 'floor', h: WALL_H, name: 'Couloir de service' },
  { id: 'laundDown', x0: 6, z0: 24, x1: 6, z1: 24, wall: 'wall', floor: 'floor', h: WALL_H, name: 'Couloir de service' },
  { id: 'utilDown', x0: 16, z0: 24, x1: 16, z1: 24, wall: 'wall', floor: 'floor', h: WALL_H, name: 'Couloir de service' },

  { id: 'wcLink', x0: 4, z0: 27, x1: 4, z1: 27, wall: 'tileWhite', floor: 'tile', h: WALL_H, name: 'Sanitaires' },
  { id: 'toilets', x0: 2, z0: 28, x1: 7, z1: 32, wall: 'tileWhite', floor: 'tile', h: WALL_H, name: 'Sanitaires' },

  { id: 'infLink', x0: 11, z0: 27, x1: 11, z1: 27, wall: 'tileWhite', floor: 'tile', h: WALL_H, name: 'Infirmerie' },
  { id: 'infirmary', x0: 9, z0: 28, x1: 14, z1: 32, wall: 'tileWhite', floor: 'tile', h: WALL_H, name: 'Infirmerie' },

  { id: 'visitLink', x0: 17, z0: 27, x1: 17, z1: 27, wall: 'wall', floor: 'tile', h: WALL_H, name: 'Parloir' },
  { id: 'visitRoom', x0: 15, z0: 28, x1: 20, z1: 32, wall: 'wall', floor: 'tile', h: WALL_H, name: 'Parloir' },

  // Solitary: two narrow isolation cells in the slot between the guard post and
  // the armoury, entered from the north corridor. It must stay one tile wide:
  // columns 37 and 39 are load-bearing for the progression, since 39 is the
  // only thing keeping the armoury behind CAM-2's door.
  { id: 'holeLink', x0: 38, z0: 6, x1: 38, z1: 6, wall: 'wallCell', floor: 'floor', h: WALL_H, name: 'Quartier disciplinaire' },
  { id: 'solitary', x0: 38, z0: 7, x1: 38, z1: 12, wall: 'wallCell', floor: 'floor', h: 3.4, name: 'Quartier disciplinaire' },

  // Kitchen, behind the refectory serving line.
  { id: 'kitchLink', x0: 44, z0: 20, x1: 44, z1: 21, wall: 'tileWhite', floor: 'tile', h: WALL_H, name: 'Cuisine' },
  { id: 'kitchen', x0: 45, z0: 18, x1: 48, z1: 24, wall: 'tileWhite', floor: 'tile', h: WALL_H, name: 'Cuisine' },

  // Workshop off the north corridor.
  { id: 'workLink', x0: 33, z0: 3, x1: 34, z1: 3, wall: 'wall', floor: 'floor', h: WALL_H, name: 'Atelier' },
  { id: 'workshop', x0: 29, z0: 1, x1: 38, z1: 2, wall: 'wall', floor: 'floor', h: WALL_H, name: 'Atelier' },

  // ------------------------------------------------------------- the yard
  { id: 'yardLink', x0: 36, z0: 25, x1: 36, z1: 26, wall: 'metal', floor: 'floor', h: WALL_H, name: 'Sas de la cour' },
  { id: 'yard', x0: 24, z0: 27, x1: 45, z1: 39, wall: 'wall', floor: 'yard', h: YARD_H, outdoor: true, name: 'Cour de promenade' },
  { id: 'gateTunnel', x0: 46, z0: 32, x1: 48, z1: 33, wall: 'metal', floor: 'yard', h: WALL_H, outdoor: true, name: 'Porte principale' },

  // ------------------------------------------------------------ the backrooms
  // Behind a loose panel in the last toilet stall. Mono-yellow damp wallpaper,
  // soaked carpet, a ceiling too low, and the hum of fluorescent tubes that go
  // on further than they have any business going. Guards never path in here
  // (`nav: false`), and no camera watches it.
  { id: 'bkThroat', x0: 4, z0: 33, x1: 4, z1: 34, wall: 'wallpaperYellow', floor: 'carpetYellow', ceil: 'ceilingPanel', h: BACK_H, nav: false, back: true, name: 'Hors-plan' },
  { id: 'bkHallN', x0: 1, z0: 35, x1: 20, z1: 36, wall: 'wallpaperYellow', floor: 'carpetYellow', ceil: 'ceilingPanel', h: BACK_H, nav: false, back: true, name: 'Hors-plan' },
  { id: 'bkHallS', x0: 1, z0: 39, x1: 20, z1: 40, wall: 'wallpaperYellow', floor: 'carpetYellow', ceil: 'ceilingPanel', h: BACK_H, nav: false, back: true, name: 'Hors-plan' },
  { id: 'bkC1', x0: 2, z0: 37, x1: 3, z1: 38, wall: 'wallpaperYellow', floor: 'carpetYellow', ceil: 'ceilingPanel', h: BACK_H, nav: false, back: true, name: 'Hors-plan' },
  { id: 'bkC2', x0: 8, z0: 37, x1: 9, z1: 38, wall: 'wallpaperYellow', floor: 'carpetYellow', ceil: 'ceilingPanel', h: BACK_H, nav: false, back: true, name: 'Hors-plan' },
  { id: 'bkC3', x0: 14, z0: 37, x1: 15, z1: 38, wall: 'wallpaperYellow', floor: 'carpetYellow', ceil: 'ceilingPanel', h: BACK_H, nav: false, back: true, name: 'Hors-plan' },
  { id: 'bkC4', x0: 19, z0: 37, x1: 20, z1: 38, wall: 'wallpaperYellow', floor: 'carpetYellow', ceil: 'ceilingPanel', h: BACK_H, nav: false, back: true, name: 'Hors-plan' },
  // Spits you out behind the pallets at the bottom of the yard.
  { id: 'bkExit', x0: 21, z0: 39, x1: 23, z1: 40, wall: 'wallpaperYellow', floor: 'carpetYellow', ceil: 'ceilingPanel', h: BACK_H, nav: false, back: true, name: 'Hors-plan' },
];

// Six cells on each side of the coursive, each with its own barred gate.
for (let i = 0; i < 6; i++) {
  const x0 = 2 + i * 3;
  AREAS.push({ id: `cellN${i}`, x0, z0: 3, x1: x0 + 1, z1: 5, wall: 'wallCell', floor: 'floor', h: WALL_H, name: `Cellule N${i + 1}` });
  AREAS.push({ id: `cellDoorN${i}`, x0, z0: 6, x1: x0, z1: 6, wall: 'wallCell', floor: 'floor', h: WALL_H, name: `Cellule N${i + 1}` });
  AREAS.push({ id: `cellS${i}`, x0, z0: 10, x1: x0 + 1, z1: 12, wall: 'wallCell', floor: 'floor', h: WALL_H, name: `Cellule S${i + 1}` });
  AREAS.push({ id: `cellDoorS${i}`, x0, z0: 9, x1: x0, z1: 9, wall: 'wallCell', floor: 'floor', h: WALL_H, name: `Cellule S${i + 1}` });
}

/** Doors: rects of tiles that a sliding panel blocks until it is released. */
export const DOOR_DEFS = [
  { id: 'D2', area: 'armLink', label: 'ARMURERIE', camera: 'CAM-2', axis: 'x' },
  { id: 'D3', area: 'yardLink', label: 'SAS DE LA COUR', camera: 'CAM-3', axis: 'x', rect: [36, 25, 36, 25] },
  { id: 'D4', area: 'gateTunnel', label: 'PORTE PRINCIPALE', camera: ['CAM-4', 'CAM-5'], axis: 'z', rect: [46, 32, 46, 33] },
];

/**
 * Wall-mounted security cameras. `sweep` is the half-angle of the sweep in
 * degrees. `yaw` follows the same convention as the player: 0 looks down -Z,
 * 90 looks down -X, 180 down +Z, 270 down +X. Each one is aimed along the
 * space it is supposed to watch, never into the wall behind it.
 */
export const CAMERA_DEFS = [
  // Sweeps the length of the cell coursive, west from the sally port.
  { id: 'CAM-1', tile: [19, 7], y: 3.5, yaw: 90, sweep: 34, period: 8.0, range: 26, fov: 44, opens: null },
  // Watches the rotunda floor, south-east across the hall.
  { id: 'CAM-2', tile: [23, 5], y: 5.2, yaw: 225, sweep: 55, period: 10.0, range: 26, fov: 48, opens: 'D2' },
  // Covers the refectory, west across the tables.
  { id: 'CAM-3', tile: [42, 19], y: 5.2, yaw: 135, sweep: 50, period: 9.0, range: 28, fov: 48, opens: 'D3' },
  // The two yard cameras hang off the outer corner of each watchtower, clear
  // of the deck above them so they can be shot from the ground, and both look
  // in across the middle of the yard.
  { id: 'CAM-4', tile: [27, 30], offset: [2.5, 2.5], y: 5.4, yaw: 250, sweep: 55, period: 11.0, range: 34, fov: 46, opens: 'D4' },
  { id: 'CAM-5', tile: [43, 36], offset: [-2.5, -2.5], y: 5.4, yaw: 70, sweep: 55, period: 12.0, range: 34, fov: 46, opens: 'D4' },
  // The main spine corridor, looking east.
  { id: 'CAM-6', tile: [21, 15], y: 3.5, yaw: 270, sweep: 40, period: 7.0, range: 28, fov: 42, opens: null },
  // Inside the guard post, over the desk where the pistol sits.
  { id: 'CAM-7', tile: [36, 8], y: 3.5, yaw: 120, sweep: 35, period: 6.5, range: 20, fov: 46, opens: null },
  // The north corridor, looking west toward the rotunda.
  { id: 'CAM-8', tile: [40, 4], y: 3.5, yaw: 90, sweep: 30, period: 7.5, range: 24, fov: 44, opens: null },
];

/**
 * Guard patrol routes, given as tile waypoints. This list is the entire staff of
 * the prison: ten officers, built once at load. Nothing respawns or reinforces
 * them, so every one the player puts down is gone for the rest of the run.
 */
export const GUARD_DEFS = [
  { id: 'G1', route: [[3, 8], [18, 8], [18, 7], [3, 7]], speed: 2.4, weapon: 'pistol' },
  { id: 'G2', route: [[23, 6], [28, 6], [28, 12], [23, 12]], speed: 2.2, weapon: 'pistol' },
  { id: 'G3', route: [[33, 9], [36, 9], [36, 11], [33, 11]], speed: 1.7, weapon: 'pistol' },
  { id: 'G4', route: [[31, 5], [44, 5], [44, 4], [31, 4]], speed: 2.6, weapon: 'rifle' },
  { id: 'G5', route: [[23, 16], [44, 16], [44, 15], [23, 15]], speed: 2.5, weapon: 'pistol' },
  { id: 'G6', route: [[33, 20], [41, 20], [41, 23], [33, 23]], speed: 2.1, weapon: 'shotgun' },
  { id: 'G7', route: [[26, 29], [43, 29], [43, 33], [26, 33]], speed: 2.5, weapon: 'rifle' },
  { id: 'G8', route: [[28, 38], [42, 38], [42, 35], [28, 35]], speed: 2.3, weapon: 'shotgun' },
  { id: 'G9', route: [[25, 28], [25, 38], [30, 38], [30, 28]], speed: 2.7, weapon: 'pistol' },
  { id: 'G10', route: [[5, 16], [19, 16], [19, 15], [5, 15]], speed: 2.2, weapon: 'pistol' },
];

/** Weapons, ammo and medkits scattered around the facility. */
export const PICKUP_DEFS = [
  { kind: 'pistol', tile: [34, 8] },
  { kind: 'ammo', tile: [32, 11], amount: 24 },
  { kind: 'medkit', tile: [3, 11] },
  { kind: 'shotgun', tile: [42, 9] },
  { kind: 'rifle', tile: [44, 12] },
  { kind: 'ammo', tile: [41, 8], amount: 30 },
  { kind: 'ammo', tile: [44, 8], amount: 30 },
  { kind: 'medkit', tile: [43, 11] },
  { kind: 'ammo', tile: [17, 21], amount: 18 },
  { kind: 'medkit', tile: [8, 21] },
  { kind: 'ammo', tile: [24, 22], amount: 18 },
  { kind: 'ammo', tile: [38, 22], amount: 18 },
  { kind: 'medkit', tile: [26, 20] },
  { kind: 'ammo', tile: [30, 37], amount: 24 },
  { kind: 'medkit', tile: [40, 30] },
  // The infirmary is where the medical supplies actually are.
  { kind: 'medkit', tile: [12, 30] },
  { kind: 'medkit', tile: [12, 32] },
  { kind: 'ammo', tile: [19, 30], amount: 18 },      // parloir
  { kind: 'ammo', tile: [31, 2], amount: 18 },       // atelier
  { kind: 'medkit', tile: [46, 23] },                // cuisine
  // Payment for finding the way off-plan.
  { kind: 'rifle', tile: [11, 40] },
  { kind: 'ammo', tile: [17, 35], amount: 40 },
  { kind: 'medkit', tile: [3, 38] },
];

// Facing the barred gate at the south end of the cell (+Z).
export const PLAYER_SPAWN = { tile: [2, 4], yaw: Math.PI };
export const EXIT_TILE = [48, 32];

