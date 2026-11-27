// Rule v1.7 (contract 31): the conquest goal. A round is won at once by the player who owns the goal: ConquestShare of
// the CONQUERABLE cells (minus the HUD rounding slack). This file holds the pure geometry and threshold logic; Simulation
// caches the mask and the round end check calls Simulation.ConquestReached.
//
// Reachability finding (why the denominator is not ArenaCellCount): a head center never leaves the inset shape
// {SignedDistance <= -ArenaMargin} (R1, R4), so trail cells are cells crossed by a path inside that shape, and the capture
// flood (CaptureSolver) seeds every Void cell and the border of its box: any cell that a 4-connected path of cells whose
// center lies outside the reachable inset shape joins to the Void (or to the grid border) is "outside" for every capture
// and can never be owned. On the default square arena that rim band is about 3 cells deep (ArenaMargin 0.45 u = 3.6
// cells), roughly 2.4 % of the arena, so a strict 100 % of ArenaCellCount is out of reach. Thin necks of a country
// polygon (narrower than 2 ArenaMargin) also cut the inset shape into pieces a head cannot reach; those pieces are left
// out the same way (only the pieces that hold a player position count).
using System;
using System.Collections.Generic;

namespace PainterIO.Core
{
    public static class Conquest
    {
        /// <summary>Default SimConfig.ConquestShare: the goal as a share of the conquerable cells (1.0 = the HUD reads 100 %).</summary>
        public const double DefaultShare = 1.0;

        /// <summary>
        /// The goal is met from (share - DisplaySlack) of the conquerable cells: the HUD shows whole percents from 10 %, so
        /// 99.5 % already reads "100 %". It absorbs stair notches, cut corners and specks a real path leaves.
        /// </summary>
        public const double DisplaySlack = 0.005;

        /// <summary>
        /// The conquerable mask is built once a living player owns LazyFloor x (share - DisplaySlack) of the arena cells
        /// (every Europe level keeps more than half of its arena cells conquerable, EuropeLevelsTests), so rounds far from
        /// the goal never pay for it.
        /// </summary>
        public const double LazyFloor = 0.5;

        /// <summary>Neighbours searched (in cells) around a seed point whose own cell center lies outside the inset shape.</summary>
        public const int SeedSearchRadius = 4;

        /// <summary>
        /// The conquerable cells of a round (rule v1.7): every arena cell except the ones joined to the Void or to the grid
        /// border by a 4-connected path of arena cells that are not "head cells". Head cells are the arena cells whose
        /// center lies in the inset shape (SignedDistance &lt;= -Margin) and in a 4-connected piece of such cells holding
        /// one of the seed points (the players' positions). Returns the mask (index = j * Size + i) and its count.
        /// Pure and deterministic; O(cells) plus SignedDistance calls thinned by the 1-Lipschitz bound of the distance.
        /// </summary>
        public static bool[] ConquerableMask(Arena arena, OwnerGrid grid, IReadOnlyList<Vec2d> seeds, out int count)
        {
            if (arena == null) throw new ArgumentNullException(nameof(arena));
            if (grid == null) throw new ArgumentNullException(nameof(grid));
            int size = grid.Size;
            int n = size * size;
            byte[] cells = grid.Cells;
            bool[] inset = InsetCells(arena, grid);

            // Head cells: the pieces of the inset cells that hold a seed (every inset cell when no seed is usable).
            var head = new bool[n];
            var stack = new Stack<int>();
            bool seeded = false;
            if (seeds != null)
            {
                for (int s = 0; s < seeds.Count; s++)
                {
                    int start = NearestInset(grid, inset, seeds[s]);
                    if (start < 0 || head[start]) continue;
                    seeded = true;
                    head[start] = true;
                    stack.Push(start);
                    Flood(stack, size, k => inset[k] && !head[k], k => head[k] = true);
                }
            }
            if (!seeded) Array.Copy(inset, head, n);

            // Lost cells: non-head arena cells joined to the Void or to the grid border through non-head arena cells.
            var lost = new bool[n];
            for (int j = 0; j < size; j++)
            {
                for (int i = 0; i < size; i++)
                {
                    int k = j * size + i;
                    if (cells[k] == OwnerGrid.Void || head[k] || lost[k]) continue;
                    bool edge = i == 0 || j == 0 || i == size - 1 || j == size - 1
                                || cells[k - 1] == OwnerGrid.Void || cells[k + 1] == OwnerGrid.Void
                                || cells[k - size] == OwnerGrid.Void || cells[k + size] == OwnerGrid.Void;
                    if (!edge) continue;
                    lost[k] = true;
                    stack.Push(k);
                }
            }
            Flood(stack, size, k => cells[k] != OwnerGrid.Void && !head[k] && !lost[k], k => lost[k] = true);

            var mask = new bool[n];
            count = 0;
            for (int k = 0; k < n; k++)
            {
                if (cells[k] == OwnerGrid.Void || lost[k]) continue;
                mask[k] = true;
                count++;
            }
            return mask;
        }

        /// <summary>
        /// Cells needed to meet the goal: ceil(conquerable x (min(share, 1) - ConquestDisplaySlack)), at least 1 and at most
        /// conquerable. int.MaxValue (never met) when share is not &gt; 0 (goal off) or there is no conquerable cell.
        /// </summary>
        public static int TargetCells(int conquerable, double share)
        {
            if (conquerable <= 0 || !(share > 0.0)) return int.MaxValue;
            double s = Math.Min(1.0, share) - Conquest.DisplaySlack;
            int target = (int)Math.Ceiling(conquerable * s - 1e-9);
            if (target < 1) target = 1;
            return target > conquerable ? conquerable : target;
        }

        /// <summary>The conquest percentage shown to the player: 100 x min(owned, conquerable) / conquerable (0 when none).</summary>
        public static double Percent(int ownedCells, int conquerable)
        {
            if (conquerable <= 0 || ownedCells <= 0) return 0.0;
            return 100.0 * Math.Min(ownedCells, conquerable) / conquerable;
        }

        /// <summary>
        /// Arena cells whose center lies in the inset shape (SignedDistance &lt;= -Margin). Along each row the distance
        /// is 1-Lipschitz, so one evaluation classifies a run of cells (a small safety margin keeps the runs conservative).
        /// </summary>
        private static bool[] InsetCells(Arena arena, OwnerGrid grid)
        {
            int size = grid.Size;
            double cs = grid.CellSize, margin = arena.Margin;
            const double guard = 1e-9;
            byte[] cells = grid.Cells;
            var inset = new bool[size * size];
            for (int j = 0; j < size; j++)
            {
                int row = j * size;
                int i = 0;
                while (i < size)
                {
                    double d = arena.SignedDistance(grid.CellCenter(i, j));
                    int run;
                    if (double.IsNaN(d)) run = 1;
                    else if (d <= -margin)
                    {
                        // sd(i + k) <= d + k cs <= -margin while k cs <= -margin - d.
                        run = 1 + (int)Math.Floor(Math.Max(0.0, -margin - d - guard) / cs);
                        int end = Math.Min(size, i + run);
                        for (int x = i; x < end; x++) inset[row + x] = cells[row + x] != OwnerGrid.Void;
                    }
                    else
                    {
                        // sd(i + k) >= d - k cs > -margin while k cs < d + margin.
                        run = Math.Max(1, (int)Math.Ceiling((d + margin - guard) / cs));
                    }
                    i += run;
                }
            }
            return inset;
        }

        /// <summary>The cell of p when it is an inset cell, else the nearest inset cell within SeedSearchRadius, else -1.</summary>
        private static int NearestInset(OwnerGrid grid, bool[] inset, Vec2d p)
        {
            if (!grid.TryCellOf(p, out int ci, out int cj)) return -1;
            int size = grid.Size;
            int best = -1;
            double bestD = double.PositiveInfinity;
            for (int r = 0; r <= SeedSearchRadius && best < 0; r++)
            {
                for (int dj = -r; dj <= r; dj++)
                {
                    for (int di = -r; di <= r; di++)
                    {
                        if (Math.Max(Math.Abs(di), Math.Abs(dj)) != r) continue;
                        int i = ci + di, j = cj + dj;
                        if (i < 0 || j < 0 || i >= size || j >= size) continue;
                        int k = j * size + i;
                        if (!inset[k]) continue;
                        double d = (grid.CellCenter(i, j) - p).LengthSq;
                        if (d < bestD)
                        {
                            bestD = d;
                            best = k;
                        }
                    }
                }
            }
            return best;
        }

        /// <summary>4-connected flood from the cells already on the stack (already marked): marks every open neighbour.</summary>
        private static void Flood(Stack<int> stack, int size, Func<int, bool> open, Action<int> mark)
        {
            while (stack.Count > 0)
            {
                int k = stack.Pop();
                int j = k / size, i = k - j * size;
                if (i > 0) Visit(stack, k - 1, open, mark);
                if (i < size - 1) Visit(stack, k + 1, open, mark);
                if (j > 0) Visit(stack, k - size, open, mark);
                if (j < size - 1) Visit(stack, k + size, open, mark);
            }
        }

        private static void Visit(Stack<int> stack, int k, Func<int, bool> open, Action<int> mark)
        {
            if (!open(k)) return;
            mark(k);
            stack.Push(k);
        }
    }
}
