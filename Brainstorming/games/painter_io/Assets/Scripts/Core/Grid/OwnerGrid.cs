using System;
using System.Collections.Generic;

namespace PainterIO.Core
{
    /// <summary>
    /// Ownership grid (contract 5.3): Size x Size square cells of CellSize, index = j * Size + i, cell (0, 0) has its lower
    /// left corner at (Origin, Origin) with Origin = -HalfSize. A cell whose center lies outside the arena shape is Void
    /// (R1): it is never owned, never a wall and always "outside" for enclosure. Every other cell is an arena cell, Neutral
    /// or owned by a player (1..4 = player index + 1).
    /// Invariants: Void cells are fixed at construction and never change; CountOf is exact at all times (O(1) reads);
    /// Version changes whenever the content changes, so renderers can key texture uploads on it.
    /// </summary>
    public sealed class OwnerGrid
    {
        public const byte Neutral = 0;
        public const byte Void = 255;   // players are 1..4 (player index + 1)

        private readonly byte[] cells;
        private readonly int[] counts = new int[256];

        public OwnerGrid(Arena arena, double cellSize)
        {
            if (arena == null) throw new ArgumentNullException(nameof(arena));
            if (!(cellSize > 0.0)) throw new ArgumentOutOfRangeException(nameof(cellSize), "must be > 0");

            CellSize = cellSize;
            Origin = -arena.HalfSize;
            Size = (int)Math.Round(2.0 * arena.HalfSize / cellSize);
            if (Size <= 0) throw new ArgumentOutOfRangeException(nameof(cellSize), "grid would have no cell");
            cells = new byte[checked(Size * Size)];

            // R1: a cell is Void when its center is outside the full shape (Arena.Contains is SignedDistance <= 0).
            int arenaCells = 0;
            for (int j = 0; j < Size; j++)
            {
                int row = j * Size;
                for (int i = 0; i < Size; i++)
                {
                    if (arena.Contains(CellCenter(i, j)))
                    {
                        arenaCells++;
                    }
                    else
                    {
                        cells[row + i] = Void;
                    }
                }
            }
            ArenaCellCount = arenaCells;
            counts[Neutral] = arenaCells;
            counts[Void] = cells.Length - arenaCells;
        }

        /// <summary>Cells per side: round(2 HalfSize / CellSize) (512 with the Tuning values).</summary>
        public int Size { get; }

        public double CellSize { get; }

        /// <summary>World coordinate of the lower left grid corner on both axes: -HalfSize.</summary>
        public double Origin { get; }

        /// <summary>index = j * Size + i; outsiders must treat it as read-only (mutate through Set, FillDisc, Neutralize).</summary>
        public byte[] Cells => cells;

        /// <summary>Increments on every content change (a Set to the current owner changes nothing and keeps it).</summary>
        public int Version { get; private set; }

        /// <summary>Number of non-Void cells (the R20 denominator).</summary>
        public int ArenaCellCount { get; }

        /// <summary>Number of cells holding this value, maintained incrementally, O(1). CountOf(Void) is the Void count.</summary>
        public int CountOf(byte owner) => counts[owner];

        /// <summary>j * Size + i (no range check: callers pass in-grid coordinates).</summary>
        public int Index(int i, int j) => j * Size + i;

        /// <summary>
        /// Cell containing p with the floor convention (a point on a cell edge belongs to the cell on its right / above).
        /// False, with i = j = -1, when p is outside the grid or not finite.
        /// </summary>
        public bool TryCellOf(Vec2d p, out int i, out int j)
        {
            double fx = Math.Floor((p.X - Origin) / CellSize);
            double fy = Math.Floor((p.Y - Origin) / CellSize);
            // Written so that NaN fails every comparison.
            if (fx >= 0.0 && fx < Size && fy >= 0.0 && fy < Size)
            {
                i = (int)fx;
                j = (int)fy;
                return true;
            }
            i = -1;
            j = -1;
            return false;
        }

        /// <summary>Owner of the cell containing p; Void outside the grid.</summary>
        public byte OwnerAt(Vec2d p)
        {
            return TryCellOf(p, out int i, out int j) ? cells[j * Size + i] : Void;
        }

        public Vec2d CellCenter(int i, int j)
        {
            return new Vec2d(Origin + (i + 0.5) * CellSize, Origin + (j + 0.5) * CellSize);
        }

        /// <summary>
        /// Sets the owner of one cell. Void cells are ignored (R1: never owned). Setting the value Void is a programming
        /// error (it would corrupt ArenaCellCount) and throws. Maintains counts and Version.
        /// </summary>
        public void Set(int index, byte owner)
        {
            if ((uint)index >= (uint)cells.Length)
                throw new ArgumentOutOfRangeException(nameof(index), index, "cell index outside [0, Size * Size)");
            if (owner == Void) throw new ArgumentException("Void is fixed by the arena shape and cannot be assigned", nameof(owner));
            byte old = cells[index];
            if (old == Void || old == owner) return;
            cells[index] = owner;
            counts[old]--;
            counts[owner]++;
            unchecked { Version++; }
        }

        /// <summary>Sets every non-Void cell whose center is within radius of center (distance &lt;= radius) to owner.</summary>
        public void FillDisc(Vec2d center, double radius, byte owner)
        {
            if (owner == Void) throw new ArgumentException("Void is fixed by the arena shape and cannot be assigned", nameof(owner));
            if (!(radius >= 0.0)) return;
            GetDiscCellRange(center, radius, out int i0, out int i1, out int j0, out int j1);
            double r2 = radius * radius;
            for (int j = j0; j <= j1; j++)
            {
                double dy = Origin + (j + 0.5) * CellSize - center.Y;
                for (int i = i0; i <= i1; i++)
                {
                    double dx = Origin + (i + 0.5) * CellSize - center.X;
                    if (dx * dx + dy * dy <= r2) Set(j * Size + i, owner);
                }
            }
        }

        /// <summary>
        /// Every cell of owner becomes Neutral (elimination, R9 and R13). changed (may be null) is cleared first, then
        /// receives the indices of the freed cells in ascending order. Neutral and Void owners are a no-op.
        /// </summary>
        public void Neutralize(byte owner, List<int> changed)
        {
            changed?.Clear();
            if (owner == Neutral || owner == Void) return;
            int remaining = counts[owner];
            if (remaining == 0) return;
            if (changed != null && changed.Capacity < remaining) changed.Capacity = remaining;
            for (int k = 0; k < cells.Length && remaining > 0; k++)
            {
                if (cells[k] != owner) continue;
                cells[k] = Neutral;
                changed?.Add(k);
                remaining--;
            }
            counts[Neutral] += counts[owner];
            counts[owner] = 0;
            unchecked { Version++; }
        }

        /// <summary>
        /// Inclusive cell index range (clamped to the grid) covering every cell whose center can be within radius of
        /// center. The range is empty (i0 &gt; i1 or j0 &gt; j1) when the disc misses the grid.
        /// </summary>
        internal void GetDiscCellRange(Vec2d center, double radius, out int i0, out int i1, out int j0, out int j1)
        {
            // Center x_c = Origin + (i + 0.5) cs lies in [cx - r, cx + r]  <=>  i in [(cx - r - Origin)/cs - 0.5, ...].
            i0 = ClampIndex(Math.Ceiling((center.X - radius - Origin) / CellSize - 0.5));
            i1 = ClampIndex(Math.Floor((center.X + radius - Origin) / CellSize - 0.5));
            j0 = ClampIndex(Math.Ceiling((center.Y - radius - Origin) / CellSize - 0.5));
            j1 = ClampIndex(Math.Floor((center.Y + radius - Origin) / CellSize - 0.5));
            // A disc entirely off one side clamps both ends to the same border cell: make the range empty instead.
            if (center.X + radius < Origin || center.X - radius > Origin + Size * CellSize ||
                center.Y + radius < Origin || center.Y - radius > Origin + Size * CellSize ||
                double.IsNaN(center.X) || double.IsNaN(center.Y))
            {
                i0 = 0; i1 = -1; j0 = 0; j1 = -1;
            }
        }

        private int ClampIndex(double v)
        {
            if (!(v > 0.0)) return 0;          // also maps NaN to 0
            if (v >= Size - 1) return Size - 1;
            return (int)v;
        }
    }
}
