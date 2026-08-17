/**
 * AIGUILLAGE - level data.
 *
 * Every level is authored as an explicit, small node/segment/switch graph
 * (never a randomly generated one) plus a deterministic spawn table. This
 * file has zero dependency on three.js or on the simulation: it only ever
 * produces plain data that network.js and trains.js understand.
 */

export const COLORS = {
  RED: '#e0574a',
  BLUE: '#4b9fe8',
  YELLOW: '#e0c23c',
  GREEN: '#57c47a',
};

// ---------------------------------------------------------------------------
// Tiny graph builder shared by every level below.
// ---------------------------------------------------------------------------
function makeBuilder() {
  const nodes = [];
  const segments = [];
  const switches = [];

  function findNode(id) {
    for (const n of nodes) if (n.id === id) return n;
    throw new Error('unknown node ' + id);
  }

  return {
    node(id, kind, x, z, color) {
      nodes.push({ id, kind, x, z, color: color || null });
      return id;
    },
    /** Straight-ish segment with one auto midpoint control point. */
    link(id, aId, bId, crossing) {
      const a = findNode(aId);
      const b = findNode(bId);
      const points = [
        { x: a.x, z: a.z },
        { x: (a.x + b.x) / 2, z: (a.z + b.z) / 2 },
        { x: b.x, z: b.z },
      ];
      segments.push({ id, a: aId, b: bId, points, crossing: crossing || null });
      return id;
    },
    sw(id, nodeId, trunkSeg, branchASeg, branchBSeg, initialState) {
      switches.push({
        id,
        nodeId,
        trunk: trunkSeg,
        branchA: branchASeg,
        branchB: branchBSeg,
        initialState: initialState || 0,
      });
      return id;
    },
    build() {
      return { nodes, segments, switches };
    },
  };
}

// ---------------------------------------------------------------------------
// Level 1 - one switch. Teaches: a click always flips the switch, and the
// train follows whichever branch is live the instant its nose reaches it.
// ---------------------------------------------------------------------------
function net1() {
  const B = makeBuilder();
  B.node('S1', 'spawn', 0, 0);
  B.node('SW1n', 'switch', 60, 0);
  B.node('ER', 'exit', 120, -26, COLORS.RED);
  B.node('EB', 'exit', 120, 26, COLORS.BLUE);
  B.link('segIn', 'S1', 'SW1n');
  B.link('segR', 'SW1n', 'ER');
  B.link('segB', 'SW1n', 'EB');
  B.sw('SW1', 'SW1n', 'segIn', 'segR', 'segB', 0);
  return B.build();
}

// ---------------------------------------------------------------------------
// Level 2 - two spawns share one merge switch before a second switch sorts
// colours into exits. Teaches: a switch also decides who merges through.
// ---------------------------------------------------------------------------
function net2() {
  const B = makeBuilder();
  B.node('S1', 'spawn', 0, -24);
  B.node('S2', 'spawn', 0, 24);
  B.node('SW1n', 'switch', 60, 0);
  B.node('SW2n', 'switch', 130, 0);
  B.node('ER', 'exit', 190, -26, COLORS.RED);
  B.node('EB', 'exit', 190, 26, COLORS.BLUE);
  B.link('segS1', 'S1', 'SW1n');
  B.link('segS2', 'S2', 'SW1n');
  B.link('segTrunk', 'SW1n', 'SW2n');
  B.link('segR', 'SW2n', 'ER');
  B.link('segB', 'SW2n', 'EB');
  B.sw('SW1', 'SW1n', 'segTrunk', 'segS1', 'segS2', 0);
  B.sw('SW2', 'SW2n', 'segTrunk', 'segR', 'segB', 0);
  return B.build();
}

// ---------------------------------------------------------------------------
// Level 3 - a dead end siding tees off the through line. Teaches: click its
// mouth (or the parked train) to send it back the way it came.
// ---------------------------------------------------------------------------
function net3() {
  const B = makeBuilder();
  B.node('S1', 'spawn', 0, 0);
  B.node('SW1n', 'switch', 55, 0);
  B.node('SIDE', 'siding', 95, -34);
  B.node('SW2n', 'switch', 115, 0);
  B.node('ER', 'exit', 175, -22, COLORS.RED);
  B.node('EB', 'exit', 175, 22, COLORS.BLUE);
  B.link('segIn', 'S1', 'SW1n');
  B.link('segSide', 'SW1n', 'SIDE');
  B.link('segMid', 'SW1n', 'SW2n');
  B.link('segR', 'SW2n', 'ER');
  B.link('segB', 'SW2n', 'EB');
  B.sw('SW1', 'SW1n', 'segIn', 'segSide', 'segMid', 1);
  B.sw('SW2', 'SW2n', 'segMid', 'segR', 'segB', 0);
  return B.build();
}

// ---------------------------------------------------------------------------
// Level 4 - a level crossing sits on the shared trunk. Teaches: trains queue
// safely behind a closed barrier, on a known, fixed timetable.
// ---------------------------------------------------------------------------
function net4() {
  const B = makeBuilder();
  B.node('S1', 'spawn', 0, -26);
  B.node('S2', 'spawn', 0, 26);
  B.node('SW1n', 'switch', 55, 0);
  B.node('SW2n', 'switch', 190, 0);
  B.node('ER', 'exit', 250, -26, COLORS.RED);
  B.node('EB', 'exit', 250, 26, COLORS.BLUE);
  B.link('segS1', 'S1', 'SW1n');
  B.link('segS2', 'S2', 'SW1n');
  B.link('segTrunk', 'SW1n', 'SW2n', { at: 0.5, offset: 5, closedFor: 6, period: 15 });
  B.link('segR', 'SW2n', 'ER');
  B.link('segB', 'SW2n', 'EB');
  B.sw('SW1', 'SW1n', 'segTrunk', 'segS1', 'segS2', 0);
  B.sw('SW2', 'SW2n', 'segTrunk', 'segR', 'segB', 0);
  return B.build();
}

// ---------------------------------------------------------------------------
// Level 5 - siding, crossing and three colours together.
// ---------------------------------------------------------------------------
function net5() {
  const B = makeBuilder();
  B.node('S1', 'spawn', 0, -26);
  B.node('S2', 'spawn', 0, 26);
  B.node('SW1n', 'switch', 55, 0);
  B.node('SW1bn', 'switch', 100, 0);
  B.node('SIDE', 'siding', 140, -38);
  B.node('SW2n', 'switch', 195, 0);
  B.node('EY', 'exit', 250, -34, COLORS.YELLOW);
  B.node('SW3n', 'switch', 250, 22);
  B.node('ER', 'exit', 305, 4, COLORS.RED);
  B.node('EB', 'exit', 305, 44, COLORS.BLUE);
  B.link('segS1', 'S1', 'SW1n');
  B.link('segS2', 'S2', 'SW1n');
  B.link('segTrunk1', 'SW1n', 'SW1bn');
  B.link('segSide', 'SW1bn', 'SIDE');
  B.link('segTrunk2', 'SW1bn', 'SW2n', { at: 0.5, offset: 6, closedFor: 6, period: 16 });
  B.link('segY', 'SW2n', 'EY');
  B.link('segTrunk3', 'SW2n', 'SW3n');
  B.link('segR', 'SW3n', 'ER');
  B.link('segB', 'SW3n', 'EB');
  B.sw('SW1', 'SW1n', 'segTrunk1', 'segS1', 'segS2', 0);
  B.sw('SW1b', 'SW1bn', 'segTrunk2', 'segSide', 'segTrunk1', 1);
  B.sw('SW2', 'SW2n', 'segTrunk2', 'segY', 'segTrunk3', 1);
  B.sw('SW3', 'SW3n', 'segTrunk3', 'segR', 'segB', 0);
  return B.build();
}

// ---------------------------------------------------------------------------
// Level 6 - a double (coupled) train. Teaches: it splits by itself the
// instant its nose crosses the switch, then each half is on its own.
// ---------------------------------------------------------------------------
function net6() {
  const B = makeBuilder();
  B.node('S1', 'spawn', 0, 0);
  B.node('SW1n', 'switch', 70, 0);
  B.node('ER', 'exit', 135, -26, COLORS.RED);
  B.node('EB', 'exit', 135, 26, COLORS.BLUE);
  B.link('segIn', 'S1', 'SW1n');
  B.link('segR', 'SW1n', 'ER');
  B.link('segB', 'SW1n', 'EB');
  B.sw('SW1', 'SW1n', 'segIn', 'segR', 'segB', 0);
  return B.build();
}

// ---------------------------------------------------------------------------
// Level 7 - three spawns, three colours: merge, merge, then a two step
// diverge cascade. Every switch has exactly one trunk and two branches.
// ---------------------------------------------------------------------------
function net7() {
  const B = makeBuilder();
  B.node('S1', 'spawn', 0, -40);
  B.node('S2', 'spawn', 0, 0);
  B.node('S3', 'spawn', 0, 40);
  B.node('SW1n', 'switch', 55, -20);
  B.node('SW2n', 'switch', 115, 0);
  B.node('SW3n', 'switch', 175, -10);
  B.node('SW4n', 'switch', 235, 14);
  B.node('EY', 'exit', 235, -40, COLORS.YELLOW);
  B.node('ER', 'exit', 295, -6, COLORS.RED);
  B.node('EB', 'exit', 295, 40, COLORS.BLUE);
  B.link('segS1', 'S1', 'SW1n');
  B.link('segS2', 'S2', 'SW1n');
  B.link('segTrunkA', 'SW1n', 'SW2n');
  B.link('segS3', 'S3', 'SW2n');
  B.link('segTrunkB', 'SW2n', 'SW3n');
  B.link('segY', 'SW3n', 'EY');
  B.link('segTrunkC', 'SW3n', 'SW4n');
  B.link('segR', 'SW4n', 'ER');
  B.link('segB', 'SW4n', 'EB');
  B.sw('SW1', 'SW1n', 'segTrunkA', 'segS1', 'segS2', 0);
  B.sw('SW2', 'SW2n', 'segTrunkB', 'segTrunkA', 'segS3', 0);
  B.sw('SW3', 'SW3n', 'segTrunkB', 'segY', 'segTrunkC', 0);
  B.sw('SW4', 'SW4n', 'segTrunkC', 'segR', 'segB', 0);
  return B.build();
}

// ---------------------------------------------------------------------------
// Level 8 - crossing, siding and a double train sharing one yard.
// ---------------------------------------------------------------------------
function net8() {
  const B = makeBuilder();
  B.node('S1', 'spawn', 0, -26);
  B.node('S2', 'spawn', 0, 26);
  B.node('SW1n', 'switch', 55, 0);
  B.node('SW1bn', 'switch', 100, 0);
  B.node('SIDE', 'siding', 140, -38);
  B.node('SW2n', 'switch', 210, 0);
  B.node('ER', 'exit', 265, -26, COLORS.RED);
  B.node('EB', 'exit', 265, 26, COLORS.BLUE);
  B.link('segS1', 'S1', 'SW1n');
  B.link('segS2', 'S2', 'SW1n');
  B.link('segTrunk1', 'SW1n', 'SW1bn');
  B.link('segSide', 'SW1bn', 'SIDE');
  B.link('segTrunk2', 'SW1bn', 'SW2n', { at: 0.5, offset: 7, closedFor: 6, period: 17 });
  B.link('segR', 'SW2n', 'ER');
  B.link('segB', 'SW2n', 'EB');
  B.sw('SW1', 'SW1n', 'segTrunk1', 'segS1', 'segS2', 0);
  B.sw('SW1b', 'SW1bn', 'segTrunk2', 'segSide', 'segTrunk1', 1);
  B.sw('SW2', 'SW2n', 'segTrunk2', 'segR', 'segB', 0);
  return B.build();
}

// ---------------------------------------------------------------------------
// Level 9 - four colours, five switches, no safety net but distance.
// ---------------------------------------------------------------------------
function net9() {
  const B = makeBuilder();
  B.node('S1', 'spawn', 0, -40);
  B.node('S2', 'spawn', 0, 40);
  B.node('SW1n', 'switch', 55, 0);
  B.node('SW2n', 'switch', 115, 0);
  B.node('SW3n', 'switch', 175, -24);
  B.node('SW4n', 'switch', 175, 24);
  B.node('EY', 'exit', 235, -50, COLORS.YELLOW);
  B.node('ER', 'exit', 235, -6, COLORS.RED);
  B.node('EG', 'exit', 235, 36, COLORS.GREEN);
  B.node('EB', 'exit', 235, 70, COLORS.BLUE);
  B.link('segS1', 'S1', 'SW1n');
  B.link('segS2', 'S2', 'SW1n');
  B.link('segTrunk', 'SW1n', 'SW2n');
  B.link('segLeft', 'SW2n', 'SW3n');
  B.link('segRight', 'SW2n', 'SW4n');
  B.link('segY', 'SW3n', 'EY');
  B.link('segR', 'SW3n', 'ER');
  B.link('segG', 'SW4n', 'EG');
  B.link('segB', 'SW4n', 'EB');
  B.sw('SW1', 'SW1n', 'segTrunk', 'segS1', 'segS2', 0);
  B.sw('SW2', 'SW2n', 'segTrunk', 'segLeft', 'segRight', 0);
  B.sw('SW3', 'SW3n', 'segLeft', 'segY', 'segR', 0);
  B.sw('SW4', 'SW4n', 'segRight', 'segG', 'segB', 0);
  return B.build();
}

// ---------------------------------------------------------------------------
// Level 10 - double trains, crossing and siding, tighter timetable.
// ---------------------------------------------------------------------------
function net10() {
  const B = makeBuilder();
  B.node('S1', 'spawn', 0, -26);
  B.node('S2', 'spawn', 0, 26);
  B.node('SW1n', 'switch', 55, 0);
  B.node('SIDEn', 'switch', 100, 0);
  B.node('SIDE', 'siding', 140, -38);
  B.node('SW2n', 'switch', 210, 0);
  B.node('EY', 'exit', 265, -26, COLORS.YELLOW);
  B.node('ER', 'exit', 265, 26, COLORS.RED);
  B.link('segS1', 'S1', 'SW1n');
  B.link('segS2', 'S2', 'SW1n');
  B.link('segTrunk1', 'SW1n', 'SIDEn');
  B.link('segSide', 'SIDEn', 'SIDE');
  B.link('segTrunk2', 'SIDEn', 'SW2n', { at: 0.5, offset: 6, closedFor: 5, period: 13 });
  B.link('segY', 'SW2n', 'EY');
  B.link('segR', 'SW2n', 'ER');
  B.sw('SW1', 'SW1n', 'segTrunk1', 'segS1', 'segS2', 0);
  B.sw('SIDESW', 'SIDEn', 'segTrunk2', 'segSide', 'segTrunk1', 1);
  B.sw('SW2', 'SW2n', 'segTrunk2', 'segY', 'segR', 0);
  return B.build();
}

// ---------------------------------------------------------------------------
// Level 11 - large yard, four colours, two double trains, fast timetable.
// ---------------------------------------------------------------------------
function net11() {
  const B = makeBuilder();
  B.node('S1', 'spawn', 0, -40);
  B.node('S2', 'spawn', 0, 0);
  B.node('S3', 'spawn', 0, 40);
  B.node('SW1n', 'switch', 55, -20);
  B.node('SW2n', 'switch', 115, 0);
  B.node('SIDEn', 'switch', 165, -30);
  B.node('SIDE', 'siding', 205, -60);
  B.node('SW3n', 'switch', 230, -18);
  B.node('SW4n', 'switch', 285, -34);
  B.node('SW5n', 'switch', 285, 8);
  B.node('EY', 'exit', 290, -70, COLORS.YELLOW);
  B.node('ER', 'exit', 340, -46, COLORS.RED);
  B.node('EG', 'exit', 340, -8, COLORS.GREEN);
  B.node('EB', 'exit', 340, 34, COLORS.BLUE);
  B.link('segS1', 'S1', 'SW1n');
  B.link('segS2', 'S2', 'SW1n');
  B.link('segTrunkA', 'SW1n', 'SW2n');
  B.link('segS3', 'S3', 'SW2n');
  B.link('segTrunkB', 'SW2n', 'SIDEn');
  B.link('segSide', 'SIDEn', 'SIDE');
  B.link('segTrunkC', 'SIDEn', 'SW3n');
  B.link('segY', 'SW3n', 'EY');
  B.link('segTrunkD', 'SW3n', 'SW4n');
  B.link('segR', 'SW4n', 'ER');
  B.link('segTrunkE', 'SW4n', 'SW5n');
  B.link('segG', 'SW5n', 'EG');
  B.link('segB', 'SW5n', 'EB');
  B.sw('SW1', 'SW1n', 'segTrunkA', 'segS1', 'segS2', 0);
  B.sw('SW2', 'SW2n', 'segTrunkB', 'segTrunkA', 'segS3', 0);
  B.sw('SIDESW', 'SIDEn', 'segTrunkC', 'segSide', 'segTrunkB', 1);
  B.sw('SW3', 'SW3n', 'segTrunkC', 'segY', 'segTrunkD', 0);
  B.sw('SW4', 'SW4n', 'segTrunkD', 'segR', 'segTrunkE', 0);
  B.sw('SW5', 'SW5n', 'segTrunkE', 'segG', 'segB', 0);
  return B.build();
}

// ---------------------------------------------------------------------------
// Level 12 - finale: merge cascade, a level crossing on the shared trunk, a
// siding tee, then a three switch diverge cascade down to four exits.
// ---------------------------------------------------------------------------
function buildNet12() {
  const B = makeBuilder();
  B.node('S1', 'spawn', 0, -40);
  B.node('S2', 'spawn', 0, 0);
  B.node('S3', 'spawn', 0, 40);
  B.node('SW1n', 'switch', 55, -20);
  B.node('SW2n', 'switch', 115, 0);
  B.node('SIDEn', 'switch', 235, -12);
  B.node('SIDE', 'siding', 275, -46);
  B.node('SW3n', 'switch', 290, 0);
  B.node('SW4n', 'switch', 345, -22);
  B.node('SW5n', 'switch', 345, 22);
  B.node('EY', 'exit', 350, -60, COLORS.YELLOW);
  B.node('ER', 'exit', 400, -46, COLORS.RED);
  B.node('EG', 'exit', 400, -6, COLORS.GREEN);
  B.node('EB', 'exit', 400, 40, COLORS.BLUE);
  B.link('segS1', 'S1', 'SW1n');
  B.link('segS2', 'S2', 'SW1n');
  B.link('segTrunkA', 'SW1n', 'SW2n');
  B.link('segS3', 'S3', 'SW2n');
  B.link('segTrunkB', 'SW2n', 'SIDEn', { at: 0.5, offset: 5, closedFor: 5, period: 12 });
  B.link('segSide', 'SIDEn', 'SIDE');
  B.link('segTrunkC', 'SIDEn', 'SW3n');
  B.link('segY', 'SW3n', 'EY');
  B.link('segTrunkD', 'SW3n', 'SW4n');
  B.link('segR', 'SW4n', 'ER');
  B.link('segTrunkE', 'SW4n', 'SW5n');
  B.link('segG', 'SW5n', 'EG');
  B.link('segB', 'SW5n', 'EB');
  B.sw('SW1', 'SW1n', 'segTrunkA', 'segS1', 'segS2', 0);
  B.sw('SW2', 'SW2n', 'segTrunkB', 'segTrunkA', 'segS3', 0);
  B.sw('SIDESW', 'SIDEn', 'segTrunkC', 'segSide', 'segTrunkB', 1);
  B.sw('SW3', 'SW3n', 'segTrunkC', 'segY', 'segTrunkD', 0);
  B.sw('SW4', 'SW4n', 'segTrunkD', 'segR', 'segTrunkE', 0);
  B.sw('SW5', 'SW5n', 'segTrunkE', 'segG', 'segB', 0);
  return B.build();
}

// ---------------------------------------------------------------------------
// Spawn table helpers.
// ---------------------------------------------------------------------------
function alt(nodeId, colors, start, step, count) {
  const out = [];
  for (let i = 0; i < count; i++) {
    out.push({ t: start + i * step, nodeId, color: colors[i % colors.length] });
  }
  return out;
}

function mix(...lists) {
  return lists.flat();
}

function withDoubles(nodeId, entries) {
  return entries.map((e) => ({ t: e.t, nodeId, color: e.colorA, secondColor: e.colorB }));
}

const { RED, BLUE, YELLOW, GREEN } = COLORS;

// ---------------------------------------------------------------------------
// Level catalogue.
// ---------------------------------------------------------------------------
const RAW_LEVELS = [
  {
    id: 'l01',
    name: 'Premier aiguillage',
    teach: "Cliquez l'aiguillage pour choisir la sortie : rouge ou bleue.",
    network: net1,
    spawns: alt('S1', [RED, BLUE], 3, 8, 10),
    graceSeconds: 42,
  },
  {
    id: 'l02',
    name: 'Convergence',
    teach: 'Deux voies partagent un aiguillage avant de se separer par couleur.',
    network: net2,
    spawns: mix(alt('S1', [RED, BLUE], 3, 11, 8), alt('S2', [BLUE, RED], 8, 11, 8)),
    graceSeconds: 55,
  },
  {
    id: 'l03',
    name: 'Voie d\'attente',
    teach: "Une voie sans issue peut stocker un train : cliquez pour le faire repartir en arriere.",
    network: net3,
    spawns: alt('S1', [RED, BLUE], 3, 9, 11),
    graceSeconds: 48,
  },
  {
    id: 'l04',
    name: 'Passage a niveau',
    teach: null,
    network: net4,
    spawns: mix(alt('S1', [RED, BLUE], 3, 12, 8), alt('S2', [BLUE, RED], 9, 12, 8)),
    graceSeconds: 60,
  },
  {
    id: 'l05',
    name: 'Triage aux trois couleurs',
    teach: null,
    network: net5,
    spawns: mix(
      alt('S1', [RED, YELLOW, BLUE], 3, 10, 10),
      alt('S2', [BLUE, RED, YELLOW], 7, 10, 9),
    ),
    graceSeconds: 62,
  },
  {
    id: 'l06',
    name: 'Rame double',
    teach: 'Une rame a deux couleurs se separe seule au passage de l\'aiguillage.',
    network: net6,
    spawns: mix(
      withDoubles('S1', [
        { t: 4, colorA: RED, colorB: BLUE },
        { t: 26, colorA: BLUE, colorB: RED },
        { t: 48, colorA: RED, colorB: BLUE },
        { t: 70, colorA: BLUE, colorB: RED },
      ]),
      alt('S1', [RED, BLUE], 14, 8, 3),
    ),
    graceSeconds: 40,
  },
  {
    id: 'l07',
    name: 'Triage a trois entrees',
    teach: null,
    network: net7,
    spawns: mix(
      alt('S1', [YELLOW, RED], 3, 9, 8),
      alt('S2', [RED, BLUE], 6, 9, 8),
      alt('S3', [BLUE, YELLOW], 9, 9, 8),
    ),
    graceSeconds: 60,
  },
  {
    id: 'l08',
    name: 'Nuit chargee',
    teach: null,
    network: net8,
    spawns: mix(alt('S1', [RED, BLUE], 3, 9, 10), alt('S2', [BLUE, RED], 7, 9, 10)),
    graceSeconds: 58,
  },
  {
    id: 'l09',
    name: 'Grand triage',
    teach: null,
    network: net9,
    spawns: mix(
      alt('S1', [YELLOW, RED, GREEN, BLUE], 3, 7, 12),
      alt('S2', [BLUE, GREEN, RED, YELLOW], 6, 7, 12),
    ),
    graceSeconds: 65,
  },
  {
    id: 'l10',
    name: 'Rames doubles serrees',
    teach: null,
    network: net10,
    spawns: mix(
      withDoubles('S1', [
        { t: 3, colorA: YELLOW, colorB: RED },
        { t: 24, colorA: RED, colorB: YELLOW },
        { t: 45, colorA: YELLOW, colorB: RED },
      ]),
      alt('S2', [RED, YELLOW], 10, 8, 8),
    ),
    graceSeconds: 55,
  },
  {
    id: 'l11',
    name: 'Reseau tentaculaire',
    teach: null,
    network: net11,
    spawns: mix(
      alt('S1', [YELLOW, RED], 3, 7, 10),
      alt('S2', [GREEN, BLUE], 5, 7, 10),
      withDoubles('S3', [
        { t: 8, colorA: BLUE, colorB: GREEN },
        { t: 40, colorA: RED, colorB: YELLOW },
        { t: 72, colorA: GREEN, colorB: BLUE },
      ]),
    ),
    graceSeconds: 66,
  },
  {
    id: 'l12',
    name: 'Poste central',
    teach: null,
    network: buildNet12,
    spawns: mix(
      alt('S1', [YELLOW, RED], 3, 6, 12),
      alt('S2', [GREEN, BLUE], 5, 6, 12),
      withDoubles('S3', [
        { t: 9, colorA: RED, colorB: GREEN },
        { t: 33, colorA: BLUE, colorB: YELLOW },
        { t: 57, colorA: GREEN, colorB: RED },
        { t: 81, colorA: YELLOW, colorB: BLUE },
      ]),
    ),
    graceSeconds: 70,
  },
];

export const LEVELS = RAW_LEVELS.map((lvl, index) => ({
  index,
  id: lvl.id,
  name: lvl.name,
  teach: lvl.teach,
  pauseBudget: 10,
  graceSeconds: lvl.graceSeconds,
  network: lvl.network(),
  spawns: lvl.spawns,
  trainCount: lvl.spawns.length,
}));

export function levelCount() {
  return LEVELS.length;
}

export function getLevel(index) {
  return LEVELS[Math.max(0, Math.min(LEVELS.length - 1, index))];
}
