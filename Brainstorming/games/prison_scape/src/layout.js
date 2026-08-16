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
 * the prison: fourteen officers, built once at load. Nothing respawns or
 * reinforces them, so every one the player puts down is gone for the rest of
 * the run.
 *
 * Three rules a new route has to respect, all of them learned the hard way:
 *
 * 1. Every waypoint sits on an open tile that is walkable from the spawn with
 *    all the security doors still locked. `tools/check-level.mjs` asserts the
 *    first half; the second is on you. A waypoint behind a locked door leaves
 *    its officer facing a wall for the whole run.
 * 2. A guard walks between two waypoints in a straight line when he can see the
 *    next one, and follows the flow field over the tiles when he cannot. The
 *    flow field knows about walls and doors but not about furniture, so both the
 *    straight line and the tiles in between have to be clear of props. Rooms are
 *    entered along the lane the furniture leaves open (the east aisle of the
 *    laundry, the x25 lane between the shower dividers, the north side of the
 *    refectory serving counter), never diagonally across the middle.
 * 3. The waypoint before a doorway sits on the doorway's own column or row. A
 *    line of sight is a ray and a guard is a box: aim him at a room from one
 *    tile off to the side and the ray slips through the opening while his
 *    shoulder is still against the wall next to it, which is a guard grinding
 *    on a corner for the rest of the run. Hence the pairs [4,26]/[4,30],
 *    [11,26]/[11,29], [17,26]/[17,28], [16,24]/[16,23] and so on.
 */
export const GUARD_DEFS = [
  { id: 'G1', route: [[3, 8], [18, 8], [18, 7], [3, 7]], speed: 2.4, weapon: 'pistol' },
  // Hugs the rotunda wall. The old loop cut across tiles 24/28 by 6 and 12,
  // which are the four pillars, and the leg out of [23,6] ran the officer
  // straight into the bench on tile 27 - he had not moved since it was put
  // there. Rule 2 above, learned here.
  { id: 'G2', route: [[23, 5], [29, 5], [29, 13], [23, 13]], speed: 2.2, weapon: 'pistol' },
  { id: 'G3', route: [[33, 9], [36, 9], [36, 11], [33, 11]], speed: 1.7, weapon: 'pistol' },
  { id: 'G4', route: [[31, 5], [44, 5], [44, 4], [31, 4]], speed: 2.6, weapon: 'rifle' },
  { id: 'G5', route: [[23, 16], [44, 16], [44, 15], [23, 15]], speed: 2.5, weapon: 'pistol' },
  { id: 'G6', route: [[33, 20], [41, 20], [41, 23], [33, 23]], speed: 2.1, weapon: 'shotgun' },
  { id: 'G7', route: [[26, 29], [43, 29], [43, 33], [26, 33]], speed: 2.5, weapon: 'rifle' },
  { id: 'G8', route: [[28, 38], [42, 38], [42, 35], [28, 35]], speed: 2.3, weapon: 'shotgun' },
  { id: 'G9', route: [[25, 28], [25, 38], [30, 38], [30, 28]], speed: 2.7, weapon: 'pistol' },
  { id: 'G10', route: [[5, 16], [19, 16], [19, 15], [5, 15]], speed: 2.2, weapon: 'pistol' },

  // Service corridor round: the whole west wing, dipping into the sanitary
  // block, the infirmary and the visiting room in turn. Each room is entered
  // straight down its own doorway column (x4, x11, x17) and left the same way,
  // which is the only line through them the furniture leaves open.
  {
    id: 'G11',
    route: [
      [4, 26], [4, 30], [4, 26],
      [11, 26], [11, 29], [11, 26],
      [17, 26], [17, 28], [17, 26],
      [18, 25], [3, 25],
    ],
    speed: 2.3,
    weapon: 'pistol',
  },

  // Utilities round: down the east aisle of the laundry, back up through the
  // service corridor into the plant room, then along the spine to the showers.
  // The x25 lane is the one gap in the row of shower dividers.
  {
    id: 'G12',
    route: [
      [7, 16], [7, 19], [8, 22], [6, 23], [6, 24],
      [16, 24], [16, 23], [17, 21], [16, 18], [16, 16],
      [25, 16], [25, 19], [26, 21], [25, 19],
    ],
    speed: 2.0,
    weapon: 'shotgun',
  },

  // North round: the workshop bench aisle, then the length of the north
  // corridor with a look down the solitary slot on the way past. He only steps
  // one tile into the slot: past that the slab bunks leave no room for him.
  // [38,5] exists purely to bring him back out of the slot on its own column
  // before he turns east - rule 3.
  {
    id: 'G13',
    route: [
      [31, 4], [33, 3], [33, 2], [31, 2], [36, 2], [34, 2], [34, 3],
      [38, 4], [38, 7], [38, 5], [42, 5], [31, 5],
    ],
    speed: 2.4,
    weapon: 'rifle',
  },

  // Kitchen round: down the west lane of the refectory, around the south end of
  // the tables, then over the serving line into the kitchen. Crossing back west
  // is done north of the serving counter, never through it, and the last leg
  // runs back along the z19 lane so he leaves the hall on the x37 doorway
  // column instead of scraping the wall beside it - rule 3.
  {
    id: 'G14',
    route: [
      [37, 16], [37, 19], [37, 22], [40, 22], [42, 19], [43, 20],
      [44, 20], [45, 20], [45, 23], [45, 21], [43, 21], [43, 19], [37, 19],
    ],
    speed: 2.1,
    weapon: 'pistol',
  },
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

