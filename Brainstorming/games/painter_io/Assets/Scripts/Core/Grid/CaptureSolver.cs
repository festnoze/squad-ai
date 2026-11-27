using System;
using System.Collections.Generic;

namespace PainterIO.Core
{
    /// <summary>
    /// Capture on return (R7, R8, contract section 7), the one-large-flood implementation:
    ///   TrailCells = RasterPolyline(outline), OwnP = cells of the player, B = bbox(OwnP, TrailCells, pocket) + 1 cell.
    ///   (i)   ReachAfter: scanline span fill from the seeds (non-wall cells on the border of B and every Void cell of B)
    ///         with walls = OwnP + TrailCells;
    ///   (ii)  U = cells of B that are not Void, not walls and not ReachAfter;
    ///   (iii) multi-source flood from the non-own trail cells that touch ReachAfter (or lie on the border of B, where
    ///         the outside begins), spreading through non-own trail cells and U cells. It is run as a scanline span fill
    ///         (the same reachable set as a cell-by-cell BFS, several times faster on large boxes). The U cells it
    ///         reaches are the Interior: they were reachable from outside before the trail was added. Unreached U cells
    ///         are holes that own territory already enclosed; they stay as they are (step 4);
    ///   Rim = trail cells 8-adjacent to the Interior (contract 23.2 D1); Captured = (Interior + Rim + pocket) minus Void
    ///   minus OwnP.
    /// The floods stay 4-connected (what is enclosed is unchanged); only the Rim looks at the 8 neighbours. A diagonal trail
    /// is rastered as a staircase of two cell diagonals and the outer one touches the Interior only at cell corners: with
    /// a 4-adjacency Rim it stayed neutral (stair notches that made a head gliding along its own diagonal edge flicker
    /// Exit / Return at about 30 Hz). A bare back-and-forth line still has no Interior, hence no Rim (C2).
    /// Pure (never mutates the grid or the pocket). Per-thread buffers are pooled by grid size: no grid-sized allocation
    /// per call, only the returned array.
    /// </summary>
    public static class CaptureSolver
    {
        // Per-cell flags of the pooled buffer. Only the cells of B are initialized and touched by a call.
        private const byte Own = 1;        // owned by the player (wall before and after)
        private const byte Trail = 2;      // trail cell (wall after), never Void
        private const byte VoidCell = 4;   // outside the arena shape: a seed, never a wall
        private const byte Reach = 8;      // ReachAfter
        private const byte Visited = 16;   // reached by the step (iii) flood (non-own trail cell or U cell)
        private const byte Rim = 32;       // trail cell 8-adjacent to the Interior (D1)
        private const byte Pocket = 64;    // pending pocket cell (R17)

        private const byte NotU = VoidCell | Own | Trail | Reach;
        // A cell stops the ReachAfter fill when it is a wall or already reached.
        private const byte ReachBlocked = Own | Trail | Reach;
        // A cell stops the step (iii) flood unless it is a non-own trail cell or a U cell not yet visited.
        private const byte InteriorBlocked = Own | VoidCell | Reach | Visited;

        /// <summary>Captured-cell test per flag byte: not Void, not own, and Interior, Rim or pocket.</summary>
        private static readonly bool[] Take = BuildTakeTable();

        /// <summary>
        /// Section 7. Pure: does not mutate g. Returns captured cell indices, ascending, excluding Void and cells already
        /// owned by player. outline = loop-erased trail (the caller runs LoopErase; this method never does); pocket may
        /// be null (its cells are added as one set union, R17).
        /// </summary>
        public static int[] Compute(OwnerGrid g, byte player, IReadOnlyList<Vec2d> outline, CellMask pocket)
        {
            if (g == null) throw new ArgumentNullException(nameof(g));
            if (player == OwnerGrid.Neutral || player == OwnerGrid.Void)
                throw new ArgumentException("player must be a player id (1..254)", nameof(player));
            if (pocket != null && pocket.Size != g.Size)
                throw new ArgumentException("pocket size " + pocket.Size + " differs from grid size " + g.Size, nameof(pocket));

            int size = g.Size;
            byte[] cells = g.Cells;
            Buffers buf = Buffers.Get(size);
            byte[] flags = buf.Flags;

            // Bounding box of OwnP, TrailCells and pocket cells (inclusive).
            int bi0 = int.MaxValue, bj0 = int.MaxValue, bi1 = int.MinValue, bj1 = int.MinValue;

            // Step 1: trail cells (non-Void, duplicates allowed) into the pooled list.
            buf.TrailCount = 0;
            if (outline != null && outline.Count > 0)
            {
                int n = outline.Count;
                if (n == 1) AddTrailSegment(g, buf, outline[0], outline[0], ref bi0, ref bj0, ref bi1, ref bj1);
                for (int k = 0; k + 1 < n; k++) AddTrailSegment(g, buf, outline[k], outline[k + 1], ref bi0, ref bj0, ref bi1, ref bj1);
            }

            // Own cells: one scan of the grid rows (skipped when the player owns nothing).
            if (g.CountOf(player) > 0) OwnBounds(cells, size, player, ref bi0, ref bj0, ref bi1, ref bj1);

            // Pocket cells.
            List<int> pocketCells = buf.PocketCells;
            pocketCells.Clear();
            if (pocket != null && pocket.Count > 0)
            {
                pocket.CopyIndices(pocketCells);
                for (int k = 0; k < pocketCells.Count; k++)
                {
                    int idx = pocketCells[k];
                    int j = idx / size, i = idx - j * size;
                    if (i < bi0) bi0 = i;
                    if (i > bi1) bi1 = i;
                    if (j < bj0) bj0 = j;
                    if (j > bj1) bj1 = j;
                }
            }

            if (bi0 > bi1) return Array.Empty<int>();   // no own cell, no trail, no pocket

            // Step 2: B = bbox grown by one cell, clamped to the grid.
            var box = new Box(size, Math.Max(bi0 - 1, 0), Math.Max(bj0 - 1, 0), Math.Min(bi1 + 1, size - 1), Math.Min(bj1 + 1, size - 1));

            // Initialize the flags of B from the owners (table lookup); every Void cell is a ReachAfter seed.
            byte[] map = buf.OwnerMap;
            map[player] = Own;
            int[] stack = buf.Stack;
            int sp = 0;
            for (int j = box.J0; j <= box.J1; j++)
            {
                int row = j * size;
                for (int idx = row + box.I0, end = row + box.I1; idx <= end; idx++)
                {
                    byte f = map[cells[idx]];
                    flags[idx] = f;
                    if (f == VoidCell)
                    {
                        if (sp == stack.Length) stack = buf.GrowStack();
                        stack[sp++] = idx;
                    }
                }
            }
            map[player] = 0;   // the map is shared by every call: restore it
            int[] trail = buf.Trail;
            int trailCount = buf.TrailCount;
            for (int k = 0; k < trailCount; k++) flags[trail[k]] |= Trail;
            for (int k = 0; k < pocketCells.Count; k++) flags[pocketCells[k]] |= Pocket;

            // Border cells of B are seeds (the outside of B is reachable by definition).
            for (int i = box.I0; i <= box.I1; i++)
            {
                sp = PushIfOpen(buf, ref stack, sp, flags, box.J0 * size + i, ReachBlocked);
                sp = PushIfOpen(buf, ref stack, sp, flags, box.J1 * size + i, ReachBlocked);
            }
            for (int j = box.J0 + 1; j < box.J1; j++)
            {
                sp = PushIfOpen(buf, ref stack, sp, flags, j * size + box.I0, ReachBlocked);
                sp = PushIfOpen(buf, ref stack, sp, flags, j * size + box.I1, ReachBlocked);
            }

            // Step (i): ReachAfter.
            SpanFill(buf, flags, box, sp, ReachBlocked, Reach);

            // Step (iii): seeds = non-own trail cells touching ReachAfter or the border of B.
            sp = 0;
            stack = buf.Stack;
            for (int k = 0; k < trailCount; k++)
            {
                int idx = trail[k];
                if ((flags[idx] & InteriorBlocked) != 0) continue;
                int j = idx / size, i = idx - j * size;
                bool seed = i == box.I0 || i == box.I1 || j == box.J0 || j == box.J1
                    || (flags[idx - 1] & Reach) != 0 || (flags[idx + 1] & Reach) != 0
                    || (flags[idx - size] & Reach) != 0 || (flags[idx + size] & Reach) != 0;
                if (!seed) continue;
                if (sp == stack.Length) stack = buf.GrowStack();
                stack[sp++] = idx;
            }
            int interiorCount = SpanFill(buf, flags, box, sp, InteriorBlocked, Visited);

            if (interiorCount == 0)
            {
                // No Interior, hence no Rim (a back-and-forth line captures nothing): only the pocket remains.
                return PocketOnly(cells, player, pocketCells);
            }

            // Step 5 (D1): Rim = trail cells 8-adjacent to an Interior cell (Interior = visited U cell). Counted once per
            // cell (the trail list may repeat a cell), own cells excluded as in step 6.
            int count = interiorCount;
            for (int k = 0; k < trailCount; k++)
            {
                int idx = trail[k];
                byte f = flags[idx];
                if ((f & (Rim | Own)) != 0) continue;
                if (TouchesInterior(flags, idx, box))
                {
                    flags[idx] = (byte)(f | Rim);
                    count++;
                }
            }
            // Pocket cells that are neither Interior nor Rim (nor own, nor Void) complete the count.
            for (int k = 0; k < pocketCells.Count; k++)
            {
                byte f = flags[pocketCells[k]];
                if ((f & (Own | VoidCell | Rim)) == 0 && !IsInterior(f)) count++;
            }

            // Step 6: Captured = (Interior + Rim + pocket) minus Void minus OwnP, ascending (row-major scan of B),
            // written straight into the exact-size result.
            var captured = new int[count];
            bool[] take = Take;
            int w = 0;
            for (int j = box.J0; j <= box.J1 && w < count; j++)
            {
                int row = j * size;
                for (int idx = row + box.I0, end = row + box.I1; idx <= end; idx++)
                {
                    if (take[flags[idx]]) captured[w++] = idx;
                }
            }
            if (w != count) throw new InvalidOperationException("CaptureSolver count mismatch: " + w + " vs " + count);
            return captured;
        }

        // A U cell (not Void, not a wall, not ReachAfter) that the step (iii) flood reached.
        private static bool IsInterior(byte f) => (f & (NotU | Visited)) == Visited;

        /// <summary>
        /// D1: true when one of the 8 neighbours of idx inside the box is an Interior cell. The cell itself is a trail cell
        /// (never Interior), so the 3 x 3 scan does not need to skip it.
        /// </summary>
        private static bool TouchesInterior(byte[] flags, int idx, in Box box)
        {
            int size = box.Size;
            int j = idx / size, i = idx - j * size;
            int iLo = i > box.I0 ? -1 : 0, iHi = i < box.I1 ? 1 : 0;
            int rowLo = j > box.J0 ? idx - size : idx, rowHi = j < box.J1 ? idx + size : idx;
            for (int row = rowLo; row <= rowHi; row += size)
            {
                for (int di = iLo; di <= iHi; di++)
                {
                    if (IsInterior(flags[row + di])) return true;
                }
            }
            return false;
        }

        private static bool[] BuildTakeTable()
        {
            var t = new bool[256];
            for (int f = 0; f < 256; f++)
            {
                byte b = (byte)f;
                t[f] = (b & (VoidCell | Own)) == 0 && (IsInterior(b) || (b & (Rim | Pocket)) != 0);
            }
            return t;
        }

        private static int PushIfOpen(Buffers buf, ref int[] stack, int sp, byte[] flags, int idx, byte blocked)
        {
            if ((flags[idx] & blocked) != 0) return sp;
            if (sp == stack.Length) stack = buf.GrowStack();
            stack[sp++] = idx;
            return sp;
        }

        /// <summary>
        /// Scanline span fill over the cells of the box whose flags have no bit of blocked, from the sp seeds already on
        /// the pooled stack; mark must be part of blocked. Each popped seed marks its whole horizontal run, then pushes one
        /// seed per open run of the rows above and below. Returns the number of marked cells that are not trail cells.
        /// </summary>
        private static int SpanFill(Buffers buf, byte[] flags, Box box, int sp, byte blocked, byte mark)
        {
            int[] stack = buf.Stack;
            int size = box.Size;
            int marked = 0;
            while (sp > 0)
            {
                int idx = stack[--sp];
                if ((flags[idx] & blocked) != 0) continue;
                int j = idx / size;
                int row = j * size;
                int left = idx, right = idx;
                int rowStart = row + box.I0, rowEnd = row + box.I1;
                while (left > rowStart && (flags[left - 1] & blocked) == 0) left--;
                while (right < rowEnd && (flags[right + 1] & blocked) == 0) right++;
                for (int k = left; k <= right; k++)
                {
                    byte f = flags[k];
                    if ((f & Trail) == 0) marked++;
                    flags[k] = (byte)(f | mark);
                }

                for (int pass = 0; pass < 2; pass++)
                {
                    int nj = pass == 0 ? j - 1 : j + 1;
                    if (nj < box.J0 || nj > box.J1) continue;
                    int offset = (nj - j) * size;
                    bool inRun = false;
                    for (int k = left + offset, end = right + offset; k <= end; k++)
                    {
                        if ((flags[k] & blocked) == 0)
                        {
                            if (!inRun)
                            {
                                if (sp == stack.Length) stack = buf.GrowStack();
                                stack[sp++] = k;
                                inRun = true;
                            }
                        }
                        else
                        {
                            inRun = false;
                        }
                    }
                }
            }
            return marked;
        }

        private static int[] PocketOnly(byte[] cells, byte player, List<int> pocketCells)
        {
            int count = 0;
            for (int k = 0; k < pocketCells.Count; k++)
            {
                byte o = cells[pocketCells[k]];
                if (o != player && o != OwnerGrid.Void) count++;
            }
            if (count == 0) return Array.Empty<int>();
            var captured = new int[count];
            int w = 0;
            for (int k = 0; k < pocketCells.Count; k++)
            {
                int idx = pocketCells[k];
                byte o = cells[idx];
                if (o != player && o != OwnerGrid.Void) captured[w++] = idx;
            }
            return captured;   // CopyIndices gave ascending order
        }

        private static void AddTrailSegment(OwnerGrid g, Buffers buf, Vec2d a, Vec2d b,
                                            ref int bi0, ref int bj0, ref int bi1, ref int bj1)
        {
            byte[] cells = g.Cells;
            int size = g.Size;
            var walker = new SegmentWalker(g, a, b);
            while (walker.Next(out int i, out int j, out double _))
            {
                int idx = j * size + i;
                if (cells[idx] == OwnerGrid.Void) continue;   // R1: Void cells are never walls
                buf.AddTrail(idx);
                if (i < bi0) bi0 = i;
                if (i > bi1) bi1 = i;
                if (j < bj0) bj0 = j;
                if (j > bj1) bj1 = j;
            }
        }

        private static void OwnBounds(byte[] cells, int size, byte player, ref int bi0, ref int bj0, ref int bi1, ref int bj1)
        {
            for (int j = 0; j < size; j++)
            {
                int row = j * size;
                int end = row + size;
                int k = row;
                while (k < end && cells[k] != player) k++;
                if (k == end) continue;
                int first = k - row;
                k = end - 1;
                while (cells[k] != player) k--;
                int last = k - row;
                if (first < bi0) bi0 = first;
                if (last > bi1) bi1 = last;
                if (j < bj0) bj0 = j;
                if (j > bj1) bj1 = j;
            }
        }

        /// <summary>The box B: inclusive cell bounds inside a grid of side Size.</summary>
        private readonly struct Box
        {
            public readonly int Size, I0, J0, I1, J1;

            public Box(int size, int i0, int j0, int i1, int j1)
            {
                Size = size;
                I0 = i0;
                J0 = j0;
                I1 = i1;
                J1 = j1;
            }
        }

        /// <summary>Per-thread buffers keyed by grid size (contract 7: no per-call allocation of grid-sized arrays).</summary>
        private sealed class Buffers
        {
            [ThreadStatic] private static Dictionary<int, Buffers> pool;

            public readonly byte[] Flags;
            public readonly byte[] OwnerMap = new byte[256];   // owner byte -> initial flags (player entry set per call)
            public int[] Stack;             // span fill seeds; grows on demand
            public int[] Trail = new int[1024];
            public int TrailCount;
            public readonly List<int> PocketCells = new List<int>();

            private Buffers(int size)
            {
                int n = size * size;
                Flags = new byte[n];
                Stack = new int[Math.Max(1024, n / 8)];
                OwnerMap[OwnerGrid.Void] = VoidCell;
            }

            public static Buffers Get(int size)
            {
                Dictionary<int, Buffers> p = pool ?? (pool = new Dictionary<int, Buffers>());
                if (!p.TryGetValue(size, out Buffers b))
                {
                    b = new Buffers(size);
                    p[size] = b;
                }
                return b;
            }

            public int[] GrowStack()
            {
                var bigger = new int[Stack.Length * 2];
                Array.Copy(Stack, bigger, Stack.Length);
                Stack = bigger;
                return bigger;
            }

            public void AddTrail(int idx)
            {
                if (TrailCount == Trail.Length)
                {
                    var bigger = new int[Trail.Length * 2];
                    Array.Copy(Trail, bigger, Trail.Length);
                    Trail = bigger;
                }
                Trail[TrailCount++] = idx;
            }
        }
    }
}
