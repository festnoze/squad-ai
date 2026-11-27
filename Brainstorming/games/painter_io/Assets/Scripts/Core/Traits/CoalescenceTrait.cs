// Owned by traits-core (wave D-1). docs/BIOME_TRAITS.md section 2: Coalescence (behaviour), P1 = MaxHoleArea (2.0 u^2).
using System;
using System.Collections.Generic;

namespace PainterIO.Core
{
    /// <summary>
    /// Coalescence: after an UNCHASED return, every hole of NEUTRAL cells fully enclosed by the returner's territory after
    /// the capture (own cells + captured cells) whose area is strictly below MaxHoleArea is filled; the filled cells join
    /// the Return's Cells (section 6 step a, before the R18 conflict rule, so a filled cell claimed by a simultaneous
    /// returner stays as it was). A hole is a 4-connected component of neutral cells whose every 4-neighbour outside it is
    /// a cell of the returner after the capture (a rival cell, a Void cell or the grid edge next to it means it is not
    /// enclosed). Area = cell count x CellSize^2. Scorched cells (ScorchedEarth) belong to the hole for the enclosure and
    /// area test but are never filled. Pre-existing holes count too (the rule looks at the territory after the capture).
    /// The result depends only on the grid and the capture, so it is identical at every tick rate.
    /// Cost: one pass over the rows for the territory box, one pass over the box, and floods that stop as soon as a
    /// component is too big, leaves the box, touches a rival or Void cell, or meets a stopped flood (same component).
    /// </summary>
    public sealed class CoalescenceTrait : ISimTrait
    {
        private int[] visit;          // per cell: id of the flood that visited it (ids grow across calls)
        private int floodId;
        private int[] stack;
        private CellMask captured;    // the capture being augmented (own-after = owned or captured)
        private readonly List<int> component = new List<int>();

        public TraitId Id => TraitId.Coalescence;

        /// <summary>Holes strictly smaller than this area (u^2) are filled (P1).</summary>
        public double MaxHoleArea { get; private set; } = TraitDefaults.CoalescenceMaxHoleArea;

        public void Attach(Simulation sim, TraitSpec spec)
        {
            MaxHoleArea = spec.P1;
        }

        public double SpeedFactor(Simulation sim, PlayerState p) => 1.0;

        public void AugmentCapture(Simulation sim, PlayerState p, List<int> cells)
        {
            if (!(MaxHoleArea > 0.0)) return;
            OwnerGrid g = sim.Grid;
            int size = g.Size;
            byte[] owner = g.Cells;
            byte id = p.Id;
            double cellArea = g.CellSize * g.CellSize;
            if (captured == null || captured.Size != size)
            {
                captured = new CellMask(size);
                visit = new int[size * size];
                stack = new int[size * size];
                floodId = 0;
            }

            // Bounding box of the territory after the capture: a hole lies strictly inside it.
            int i0 = size, i1 = -1, j0 = size, j1 = -1;
            for (int k = 0; k < cells.Count; k++)
            {
                int c = cells[k];
                captured.Set(c);
                Grow(c % size, c / size, ref i0, ref i1, ref j0, ref j1);
            }
            if (g.CountOf(id) > 0)
            {
                for (int j = 0; j < size; j++)
                {
                    int row = j * size;
                    int first = Array.IndexOf(owner, id, row, size);
                    if (first < 0) continue;
                    int last = Array.LastIndexOf(owner, id, row + size - 1, size);
                    Grow(first - row, j, ref i0, ref i1, ref j0, ref j1);
                    Grow(last - row, j, ref i0, ref i1, ref j0, ref j1);
                }
            }

            int added = 0;
            if (i1 - i0 >= 2 && j1 - j0 >= 2)
            {
                if (floodId > int.MaxValue - size * size)
                {
                    Array.Clear(visit, 0, visit.Length);
                    floodId = 0;
                }
                int callBase = floodId;
                double now = sim.TraitTime;
                for (int j = j0 + 1; j < j1; j++)
                {
                    int row = j * size;
                    for (int i = i0 + 1; i < i1; i++)
                    {
                        int c = row + i;
                        if (owner[c] != OwnerGrid.Neutral || visit[c] > callBase || captured.Get(c)) continue;
                        if (!Flood(c, size, owner, id, i0, i1, j0, j1, callBase, cellArea)) continue;
                        for (int k = 0; k < component.Count; k++)
                        {
                            int h = component[k];
                            if (sim.IsScorchedAt(h, now)) continue;
                            cells.Add(h);
                            added++;
                        }
                    }
                }
            }

            // Leave the scratch mask empty for the next call (only the bits set above).
            int original = cells.Count - added;
            for (int k = 0; k < original; k++) captured.Unset(cells[k]);
        }

        /// <summary>
        /// 4-connected flood of the neutral, not captured component of 'seed' into 'component'. True when the component is
        /// complete, enclosed (every neighbour outside it is a cell of the returner after the capture, inside the territory
        /// box) and smaller than MaxHoleArea. Stops (false) at the first proof that it is not such a hole: too many cells, a
        /// neighbour outside the box, a rival or Void neighbour, or a cell of an earlier flood of this call (an earlier
        /// complete flood would own the whole component, so that flood stopped: same component, not a hole). Every visited
        /// cell keeps this flood's id, so no cell is flooded twice in one call.
        /// </summary>
        private bool Flood(int seed, int size, byte[] owner, byte id, int i0, int i1, int j0, int j1, int callBase, double cellArea)
        {
            int me = ++floodId;
            component.Clear();
            int top = 0;
            stack[top++] = seed;
            visit[seed] = me;
            while (top > 0)
            {
                int c = stack[--top];
                component.Add(c);
                if (component.Count * cellArea >= MaxHoleArea) return false;   // too big to be filled
                int ci = c % size, cj = c / size;
                for (int d = 0; d < 4; d++)
                {
                    int ni = ci, nj = cj;
                    switch (d)
                    {
                        case 0: ni++; break;
                        case 1: ni--; break;
                        case 2: nj++; break;
                        default: nj--; break;
                    }
                    if (ni < i0 || ni > i1 || nj < j0 || nj > j1) return false;   // outside the territory box
                    int n = nj * size + ni;
                    byte o = owner[n];
                    if (o == id || captured.Get(n)) continue;                      // wall: the territory after the capture
                    if (o != OwnerGrid.Neutral) return false;                       // rival or Void cell next to it
                    int seen = visit[n];
                    if (seen == me) continue;
                    if (seen > callBase) return false;                              // a stopped flood: same component
                    visit[n] = me;
                    stack[top++] = n;
                }
            }
            return true;
        }

        private static void Grow(int i, int j, ref int i0, ref int i1, ref int j0, ref int j1)
        {
            if (i < i0) i0 = i;
            if (i > i1) i1 = i;
            if (j < j0) j0 = j;
            if (j > j1) j1 = j;
        }

        public void OnEliminated(Simulation sim, PlayerState p, int[] freedCells, double time)
        {
        }

        public void EndOfTick(Simulation sim, List<SimEvent> raised)
        {
        }
    }
}
