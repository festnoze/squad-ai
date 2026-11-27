// Owned by severed (rule v1.5, contract section 29). Pure grid analysis of a territory split by a transfer.
using System;
using System.Collections.Generic;

namespace PainterIO.Core
{
    /// <summary>
    /// Rule v1.5 (contract 29): finds the pieces a victim must lose after a transfer cut its territory in two or more.
    /// Called with the grid AFTER the transfer (pure: never mutates the grid). Definitions, for the victim v:
    ///   Lost   = cells that were v's before the transfer and now belong to another player (the transfer's victims cells),
    ///   Gained = cells that are v's now and were not before (only when v also returned in the same group),
    ///   Remain = cells that are v's now and were before, After = Remain + Gained, Before = Remain + Lost.
    /// Connectivity is 8-adjacency everywhere: the territory connectivity dual to the 4-connected outside flood of section 7
    /// (own cells that touch at a corner already close a capture) and the adjacency of the D1 rim. A piece is an 8-connected
    /// component of After; a pre-transfer territory is an 8-connected component of Before.
    /// Only the pieces produced by this split are judged: two pieces belong to the same split group when one pre-transfer
    /// territory spans both (they are joined through Lost cells). A group of two or more pieces keeps one piece: the piece
    /// holding the anchor cell when it lies in the group, else the largest piece (most cells, ties: lowest cell index). The
    /// other pieces of the group are severed, except a piece that holds cells the victim gained in this same step (its own
    /// fresh capture is never taken back). Pieces that touch no Lost cell (islands that were already separate, for example
    /// inherited land) are never visited, so they are never judged. The kept piece never loses a cell, so a victim is never
    /// eliminated by a split.
    /// Cost: a multi-source flood of After from the Remain cells next to Lost cells, stopped as soon as every seed joined
    /// one piece (the common bite that splits nothing explores only around the bite); a real split explores its pieces.
    /// Buffers are pooled per thread and grid size (stamped, never cleared per call): no grid-sized allocation per call.
    /// Deterministic: the result depends only on the grid, the lists and the anchor (fixed scan and neighbour order).
    /// </summary>
    internal static class TerritorySplit
    {
        // 8-neighbour offsets in a fixed order (E, W, N, S, NE, NW, SE, SW).
        private static readonly int[] Di = { 1, -1, 0, 0, 1, -1, 1, -1 };
        private static readonly int[] Dj = { 0, 0, 1, -1, 1, 1, -1, -1 };

        /// <summary>
        /// Appends to severedCells every cell of v that must be severed, and to severedCutter (same length) the player index
        /// of the cutter of its split group: the lowest-index player that took a Lost cell of that group. Cells come in flood
        /// order (the caller sorts). lost: cells v lost to other players in the transfer (their current owner is the taker);
        /// gained: cells v gained in the same step (may be null or empty); anchor: the cell whose piece is kept, -1 for none.
        /// Returns the number of cells appended.
        /// </summary>
        public static int Find(OwnerGrid g, byte victim, List<int> lost, int[] gained, int anchor,
                               List<int> severedCells, List<int> severedCutter)
        {
            if (g == null) throw new ArgumentNullException(nameof(g));
            if (lost == null || lost.Count == 0) return 0;
            int size = g.Size;
            byte[] cells = g.Cells;
            Buffers b = Buffers.Get(size);
            int stamp = b.NextStamp();
            int[] aux = b.Aux, auxIndex = b.AuxIndex, visit = b.Visit, label = b.Label, queue = b.Queue;

            // Lost and gained markers share one stamp array: a lost cell is not v's now, a gained cell is.
            for (int k = 0; k < lost.Count; k++)
            {
                int c = lost[k];
                aux[c] = stamp;
                auxIndex[c] = k;
            }
            if (gained != null)
            {
                for (int k = 0; k < gained.Length; k++) aux[gained[k]] = stamp;
            }

            // Seeds: Remain cells 8-adjacent to a Lost cell, one label each, in lost order then neighbour order.
            List<int> parent = b.Parent;
            parent.Clear();
            int tail = 0;
            for (int k = 0; k < lost.Count; k++)
            {
                int c = lost[k];
                int ci = c % size, cj = c / size;
                for (int d = 0; d < 8; d++)
                {
                    int ni = ci + Di[d], nj = cj + Dj[d];
                    if (ni < 0 || nj < 0 || ni >= size || nj >= size) continue;
                    int n = nj * size + ni;
                    if (cells[n] != victim || aux[n] == stamp || visit[n] == stamp) continue;   // not Remain, or seen
                    visit[n] = stamp;
                    label[n] = parent.Count;
                    parent.Add(parent.Count);
                    queue[tail++] = n;
                }
            }
            int labels = parent.Count;
            if (labels < 2) return 0;   // a single piece touches the cut: nothing is severed

            // Multi-source flood of After (8-adjacency). Labels that meet are united; stop once every seed is in one piece.
            int sets = labels;
            int head = 0;
            while (head < tail)
            {
                int c = queue[head++];
                int lc = label[c];
                int ci = c % size, cj = c / size;
                for (int d = 0; d < 8; d++)
                {
                    int ni = ci + Di[d], nj = cj + Dj[d];
                    if (ni < 0 || nj < 0 || ni >= size || nj >= size) continue;
                    int n = nj * size + ni;
                    if (cells[n] != victim) continue;
                    if (visit[n] == stamp)
                    {
                        if (Union(parent, label[n], lc))
                        {
                            sets--;
                            if (sets == 1) return 0;   // every frontier seed is in one piece: no split
                        }
                        continue;
                    }
                    visit[n] = stamp;
                    label[n] = lc;
                    queue[tail++] = n;
                }
            }

            // Every piece that touches the cut is complete: its size, lowest cell and whether it holds gained cells.
            List<int> count = b.Count, minCell = b.MinCell, group = b.Group, cutter = b.Cutter, kept = b.Kept;
            List<bool> fresh = b.Fresh;
            count.Clear();
            minCell.Clear();
            fresh.Clear();
            for (int l = 0; l < labels; l++)
            {
                count.Add(0);
                minCell.Add(int.MaxValue);
                fresh.Add(false);
            }
            for (int q = 0; q < tail; q++)
            {
                int c = queue[q];
                int r = Find(parent, label[c]);
                count[r]++;
                if (c < minCell[r]) minCell[r] = c;
                if (aux[c] == stamp) fresh[r] = true;   // v's cell marked in aux: a gained cell
            }

            // Split groups: union-find over the pieces (nodes 0..labels-1) and the Lost cells (labels + k). A Lost cell
            // joins its Lost neighbours and the pieces next to it, so one pre-transfer territory is one group.
            int nodes = labels + lost.Count;
            group.Clear();
            cutter.Clear();
            for (int x = 0; x < nodes; x++)
            {
                group.Add(x);
                cutter.Add(int.MaxValue);
            }
            for (int l = 0; l < labels; l++) Union(group, l, Find(parent, l));
            for (int k = 0; k < lost.Count; k++)
            {
                int c = lost[k];
                int ci = c % size, cj = c / size;
                for (int d = 0; d < 8; d++)
                {
                    int ni = ci + Di[d], nj = cj + Dj[d];
                    if (ni < 0 || nj < 0 || ni >= size || nj >= size) continue;
                    int n = nj * size + ni;
                    if (aux[n] == stamp)
                    {
                        if (cells[n] != victim) Union(group, labels + k, labels + auxIndex[n]);   // a Lost neighbour
                        // else: a Gained cell, not part of the pre-transfer territory: it links nothing
                    }
                    else if (cells[n] == victim && visit[n] == stamp) Union(group, labels + k, label[n]);   // a Remain cell of a piece
                }
            }
            for (int k = 0; k < lost.Count; k++)
            {
                int gRoot = Find(group, labels + k);
                int taker = cells[lost[k]];   // the current owner of a Lost cell is the player that took it (id = index + 1)
                if (taker < cutter[gRoot]) cutter[gRoot] = taker;
            }

            // Per group: how many pieces, and the kept one (anchor's piece in the group, else the largest).
            int anchorPiece = -1;
            if (anchor >= 0 && anchor < cells.Length && cells[anchor] == victim && visit[anchor] == stamp)
                anchorPiece = Find(parent, label[anchor]);
            kept.Clear();
            for (int x = 0; x < nodes; x++) kept.Add(-1);
            List<int> pieces = b.Pieces;
            pieces.Clear();
            for (int l = 0; l < labels; l++)
            {
                if (Find(parent, l) == l) pieces.Add(l);
            }
            List<int> piecesInGroup = b.PiecesInGroup;
            piecesInGroup.Clear();
            for (int x = 0; x < nodes; x++) piecesInGroup.Add(0);
            for (int p = 0; p < pieces.Count; p++) piecesInGroup[Find(group, pieces[p])]++;
            if (anchorPiece >= 0) kept[Find(group, anchorPiece)] = anchorPiece;
            for (int p = 0; p < pieces.Count; p++)
            {
                int r = pieces[p];
                int gRoot = Find(group, r);
                if (piecesInGroup[gRoot] < 2 || (anchorPiece >= 0 && Find(group, anchorPiece) == gRoot)) continue;
                int best = kept[gRoot];
                if (best < 0 || count[r] > count[best] || (count[r] == count[best] && minCell[r] < minCell[best])) kept[gRoot] = r;
            }

            // Severed: every piece of a group of two or more pieces that is not its kept piece and holds no gained cell.
            int added = 0;
            for (int q = 0; q < tail; q++)
            {
                int c = queue[q];
                int r = Find(parent, label[c]);
                int gRoot = Find(group, r);
                if (piecesInGroup[gRoot] < 2 || kept[gRoot] == r || fresh[r]) continue;
                severedCells.Add(c);
                severedCutter.Add(cutter[gRoot] == int.MaxValue ? -1 : cutter[gRoot] - 1);
                added++;
            }
            return added;
        }

        /// <summary>
        /// Rule v1.6 (single domain, contract 30): labels the 8-connected pieces of the owner's cells, counting the cells of
        /// extra (may be null; Void cells skipped) as the owner's too (a band not written yet), keeps the piece holding the
        /// anchor cell when the anchor is one of these cells, else the largest piece (most cells, ties: the piece holding the
        /// lowest cell index, exactly the v1.5 rule), and appends every cell of the other pieces to severed in ascending
        /// order (extra cells included). Returns the number of pieces (0 when the owner has no cell). Pure.
        /// Cost: a flood from the anchor that stops when it reached every cell (one piece: O(territory)); otherwise one scan
        /// of the grid plus a flood of every piece. Pooled stamped buffers, no grid-sized allocation per call.
        /// Rule v1.8 (contract 32): neighbours = 4 labels 4-connected pieces instead (cells touching only at a corner are
        /// separate), which tells a diagonal-only connection apart; 8 (the default) is the territory connectivity.
        /// </summary>
        public static int KeepOnePiece(OwnerGrid g, byte owner, List<int> extra, int anchor, List<int> severed, int neighbours = 8)
        {
            if (neighbours != 4 && neighbours != 8) throw new ArgumentOutOfRangeException(nameof(neighbours));
            if (g == null) throw new ArgumentNullException(nameof(g));
            int size = g.Size;
            byte[] cells = g.Cells;
            Buffers b = Buffers.Get(size);
            int stamp = b.NextStamp();
            int[] aux = b.Aux, visit = b.Visit, label = b.Label, queue = b.Queue;

            int total = g.CountOf(owner);
            if (extra != null)
            {
                for (int k = 0; k < extra.Count; k++)
                {
                    int c = extra[k];
                    if (c < 0 || c >= cells.Length || cells[c] == owner || cells[c] == OwnerGrid.Void || aux[c] == stamp) continue;
                    aux[c] = stamp;
                    total++;
                }
            }
            if (total == 0) return 0;

            List<int> count = b.Count, minCell = b.MinCell;
            count.Clear();
            minCell.Clear();
            int anchorLabel = -1;
            if (anchor >= 0 && anchor < cells.Length && (cells[anchor] == owner || aux[anchor] == stamp))
            {
                anchorLabel = 0;
                int reached = FloodPiece(cells, size, owner, aux, visit, label, queue, stamp, anchor, 0, neighbours, out int lowest);
                count.Add(reached);
                minCell.Add(lowest);
                if (reached == total) return 1;
            }

            // Several pieces (or no usable anchor): label every remaining piece in scan order.
            int labelled = count.Count > 0 ? count[0] : 0;
            for (int c = 0; c < cells.Length && labelled < total; c++)
            {
                if (visit[c] == stamp || !(cells[c] == owner || aux[c] == stamp)) continue;
                int l = count.Count;
                int reached = FloodPiece(cells, size, owner, aux, visit, label, queue, stamp, c, l, neighbours, out int lowest);
                count.Add(reached);
                minCell.Add(lowest);
                labelled += reached;
            }
            int pieces = count.Count;
            if (pieces <= 1) return pieces;

            int kept = anchorLabel;
            if (kept < 0)
            {
                kept = 0;
                for (int l = 1; l < pieces; l++)
                {
                    if (count[l] > count[kept] || (count[l] == count[kept] && minCell[l] < minCell[kept])) kept = l;
                }
            }
            for (int c = 0; c < cells.Length; c++)
            {
                if (visit[c] == stamp && label[c] != kept) severed.Add(c);
            }
            return pieces;
        }

        /// <summary>
        /// Rule v1.6 (single domain, contract 30): true when every cell of gained (distinct indices) is 8-connected, through
        /// gained cells, to a cell of the owner that is not in gained. Works on the grid before the gain is written (gained
        /// cells counted as the owner's) and after it. True for an empty gain. Cost O(gained). Pure.
        /// </summary>
        public static bool GainAttached(OwnerGrid g, byte owner, IReadOnlyList<int> gained)
        {
            if (g == null) throw new ArgumentNullException(nameof(g));
            if (gained == null || gained.Count == 0) return true;
            int size = g.Size;
            byte[] cells = g.Cells;
            Buffers b = Buffers.Get(size);
            int stamp = b.NextStamp();
            int[] aux = b.Aux, visit = b.Visit, queue = b.Queue;
            int distinct = 0;
            for (int k = 0; k < gained.Count; k++)
            {
                int c = gained[k];
                if (aux[c] == stamp) continue;
                aux[c] = stamp;
                distinct++;
            }
            // Seeds: gained cells next to an owner cell that is not gained.
            int tail = 0;
            for (int k = 0; k < gained.Count; k++)
            {
                int c = gained[k];
                if (visit[c] == stamp) continue;
                int ci = c % size, cj = c / size;
                for (int d = 0; d < 8; d++)
                {
                    int ni = ci + Di[d], nj = cj + Dj[d];
                    if (ni < 0 || nj < 0 || ni >= size || nj >= size) continue;
                    int n = nj * size + ni;
                    if (cells[n] != owner || aux[n] == stamp) continue;
                    visit[c] = stamp;
                    queue[tail++] = c;
                    break;
                }
            }
            int head = 0;
            while (head < tail)
            {
                int c = queue[head++];
                int ci = c % size, cj = c / size;
                for (int d = 0; d < 8; d++)
                {
                    int ni = ci + Di[d], nj = cj + Dj[d];
                    if (ni < 0 || nj < 0 || ni >= size || nj >= size) continue;
                    int n = nj * size + ni;
                    if (aux[n] != stamp || visit[n] == stamp) continue;
                    visit[n] = stamp;
                    queue[tail++] = n;
                }
            }
            return tail == distinct;
        }

        /// <summary>
        /// Floods one 8-connected (or 4-connected, neighbours = 4: the first four offsets are E, W, N, S) piece of (owner
        /// cells + cells marked in aux with stamp) from seed, marking visit and label. Returns its size and the lowest cell
        /// index in it.
        /// </summary>
        private static int FloodPiece(byte[] cells, int size, byte owner, int[] aux, int[] visit, int[] label, int[] queue,
                                      int stamp, int seed, int l, int neighbours, out int lowest)
        {
            int tail = 0, head = 0;
            visit[seed] = stamp;
            label[seed] = l;
            queue[tail++] = seed;
            lowest = seed;
            while (head < tail)
            {
                int c = queue[head++];
                if (c < lowest) lowest = c;
                int ci = c % size, cj = c / size;
                for (int d = 0; d < neighbours; d++)
                {
                    int ni = ci + Di[d], nj = cj + Dj[d];
                    if (ni < 0 || nj < 0 || ni >= size || nj >= size) continue;
                    int n = nj * size + ni;
                    if (visit[n] == stamp || !(cells[n] == owner || aux[n] == stamp)) continue;
                    visit[n] = stamp;
                    label[n] = l;
                    queue[tail++] = n;
                }
            }
            return tail;
        }

        /// <summary>
        /// The cell a trailing player left home from: the exit point (Trail.Points[0]) lies on the edge between that home
        /// cell and the first outside cell (R5), so among the cells whose closed square contains the point (two on an edge,
        /// four at a corner) it is the one the player still owns (lowest index if several). When none is owned (the cell
        /// was taken since, or the exit started at the head after a stolen cell, R9), the cell containing the point, which
        /// the player does not own. -1 outside the grid.
        /// </summary>
        public static int ExitCell(OwnerGrid g, byte player, Vec2d exitPoint)
        {
            if (g == null) throw new ArgumentNullException(nameof(g));
            const double Tol = 1e-7;   // in cells: exit points lie on edges up to rounding (~1e-13 cell)
            double fx = (exitPoint.X - g.Origin) / g.CellSize;
            double fy = (exitPoint.Y - g.Origin) / g.CellSize;
            if (double.IsNaN(fx) || double.IsNaN(fy)) return -1;
            int i0 = (int)Math.Floor(fx - Tol), i1 = (int)Math.Floor(fx + Tol);
            int j0 = (int)Math.Floor(fy - Tol), j1 = (int)Math.Floor(fy + Tol);
            for (int j = j0; j <= j1; j++)
            {
                if (j < 0 || j >= g.Size) continue;
                for (int i = i0; i <= i1; i++)
                {
                    if (i < 0 || i >= g.Size) continue;
                    int c = j * g.Size + i;
                    if (g.Cells[c] == player) return c;
                }
            }
            return g.TryCellOf(exitPoint, out int ci, out int cj) ? g.Index(ci, cj) : -1;
        }

        private static int Find(List<int> parent, int x)
        {
            int root = x;
            while (parent[root] != root) root = parent[root];
            while (parent[x] != root)
            {
                int next = parent[x];
                parent[x] = root;
                x = next;
            }
            return root;
        }

        /// <summary>Unites the sets of a and b (the lower root becomes the root). True when they were distinct.</summary>
        private static bool Union(List<int> parent, int a, int b)
        {
            int ra = Find(parent, a), rb = Find(parent, b);
            if (ra == rb) return false;
            if (ra < rb) parent[rb] = ra;
            else parent[ra] = rb;
            return true;
        }

        private sealed class Buffers
        {
            [ThreadStatic] private static Dictionary<int, Buffers> pool;

            public readonly int[] Aux, AuxIndex, Visit, Label, Queue;
            public readonly List<int> Parent = new List<int>(), Count = new List<int>(), MinCell = new List<int>();
            public readonly List<int> Group = new List<int>(), Cutter = new List<int>(), Kept = new List<int>();
            public readonly List<int> Pieces = new List<int>(), PiecesInGroup = new List<int>();
            public readonly List<bool> Fresh = new List<bool>();
            private int stamp;

            private Buffers(int size)
            {
                int n = size * size;
                Aux = new int[n];
                AuxIndex = new int[n];
                Visit = new int[n];
                Label = new int[n];
                Queue = new int[n];
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

            /// <summary>A fresh stamp for one call (the arrays are cleared only when the counter would wrap).</summary>
            public int NextStamp()
            {
                if (stamp == int.MaxValue)
                {
                    Array.Clear(Aux, 0, Aux.Length);
                    Array.Clear(Visit, 0, Visit.Length);
                    stamp = 0;
                }
                return ++stamp;
            }
        }
    }
}
