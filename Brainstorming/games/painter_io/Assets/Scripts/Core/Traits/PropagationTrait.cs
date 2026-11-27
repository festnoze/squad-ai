// Owned by traits-core (wave D-1). docs/BIOME_TRAITS.md section 2: Propagation (behaviour), P1 = Interval (4.0 s),
// P2 = Rings (1).
using System;
using System.Collections.Generic;

namespace PainterIO.Core
{
    /// <summary>
    /// Propagation: at every tick end where Time crosses a multiple of Interval (t0 &lt; k Interval &lt;= t1, with a 1e-9
    /// tolerance so tick times that are exact multiples count once), every alive player's territory grows by Rings rings.
    /// One ring: every NEUTRAL arena cell 4-adjacent to cells of exactly one player becomes that player's, except
    /// - cells 4-adjacent to cells of two or more players (they stay neutral),
    /// - cells under any live head: its current Cell and every cell whose center lies within HeadRadius of the head,
    /// - for the claiming player, the cells of its own trail raster (GridRaster.RasterPolyline of its trail, which ends at
    ///   the head) and their 4-neighbours, so propagation never triggers that player's own return,
    /// - scorched cells (ScorchedEarth).
    /// Each ring is computed against the grid left by the previous one. Emits one TerritoryGrew event per player that grew
    /// (Player, Cells ascending, Time = the tick end time), in player order. At most one growth per tick (an Interval
    /// shorter than a tick grows once per tick). Only neutral cells change, so nobody is eliminated, no home player's cell
    /// changes and a trailing player's state is untouched. With Interval a multiple of 1/6 s the instants are common tick
    /// times of 30, 60 and 144 Hz, so scripted scenarios give the same cells at every rate.
    /// </summary>
    public sealed class PropagationTrait : ISimTrait
    {
        private const double TimeTolerance = 1e-9;

        private CellMask blocked;                   // cells under live heads (all claimants)
        private CellMask trailRaster, trailBand;    // one claimant's trail raster and raster + 4-neighbours
        private readonly List<int> scratch = new List<int>();
        private readonly List<int> candidates = new List<int>();
        private readonly List<byte> claimants = new List<byte>();
        private List<int>[] grown;

        public TraitId Id => TraitId.Propagation;

        /// <summary>Seconds between growth instants (P1).</summary>
        public double Interval { get; private set; } = TraitDefaults.PropagationInterval;

        /// <summary>Rings grown at each instant (P2, rounded to a whole number).</summary>
        public int Rings { get; private set; } = (int)TraitDefaults.PropagationRings;

        public void Attach(Simulation sim, TraitSpec spec)
        {
            Interval = spec.P1;
            Rings = (int)Math.Round(spec.P2);
        }

        public double SpeedFactor(Simulation sim, PlayerState p) => 1.0;

        public void AugmentCapture(Simulation sim, PlayerState p, List<int> cells)
        {
        }

        public void OnEliminated(Simulation sim, PlayerState p, int[] freedCells, double time)
        {
        }

        public void EndOfTick(Simulation sim, List<SimEvent> raised)
        {
            if (Rings <= 0 || !(Interval > 0.0)) return;
            double t0 = sim.TickStartTime, t1 = sim.Time;
            if (Math.Floor(t1 / Interval + TimeTolerance) <= Math.Floor(t0 / Interval + TimeTolerance)) return;
            Grow(sim, raised, t1);
        }

        /// <summary>Grows every alive player by Rings rings now (also used by tests); raises the TerritoryGrew events.</summary>
        internal void Grow(Simulation sim, List<SimEvent> raised, double time)
        {
            OwnerGrid g = sim.Grid;
            IReadOnlyList<PlayerState> players = sim.Players;
            int n = players.Count;
            if (blocked == null || blocked.Size != g.Size)
            {
                blocked = new CellMask(g.Size);
                trailRaster = new CellMask(g.Size);
                trailBand = new CellMask(g.Size);
            }
            if (grown == null || grown.Length != n)
            {
                grown = new List<int>[n];
                for (int i = 0; i < n; i++) grown[i] = new List<int>();
            }
            for (int i = 0; i < n; i++) grown[i].Clear();

            BlockHeads(sim);
            for (int ring = 0; ring < Rings; ring++)
            {
                FindCandidates(sim);
                if (candidates.Count == 0) break;
                FilterOwnTrails(sim);
                for (int k = 0; k < candidates.Count; k++)
                {
                    if (candidates[k] < 0) continue;
                    byte who = claimants[k];
                    g.Set(candidates[k], who);
                    grown[who - 1].Add(candidates[k]);
                }
            }

            for (int i = 0; i < n; i++)
            {
                if (grown[i].Count == 0) continue;
                grown[i].Sort();
                raised.Add(new SimEvent { Type = SimEventType.TerritoryGrew, Time = time, Player = i, Cells = grown[i].ToArray() });
            }
        }

        /// <summary>Cells under live heads: each head's current Cell and the cells whose center is within HeadRadius.</summary>
        private void BlockHeads(Simulation sim)
        {
            OwnerGrid g = sim.Grid;
            blocked.Clear();
            double r = sim.Config.HeadRadius;
            double cs = g.CellSize, o = g.Origin;
            IReadOnlyList<PlayerState> players = sim.Players;
            for (int i = 0; i < players.Count; i++)
            {
                PlayerState p = players[i];
                if (!p.Alive) continue;
                blocked.Set(p.Cell);
                int ia = Math.Max(0, (int)Math.Floor((p.Pos.X - r - o) / cs));
                int ib = Math.Min(g.Size - 1, (int)Math.Floor((p.Pos.X + r - o) / cs));
                int ja = Math.Max(0, (int)Math.Floor((p.Pos.Y - r - o) / cs));
                int jb = Math.Min(g.Size - 1, (int)Math.Floor((p.Pos.Y + r - o) / cs));
                for (int j = ja; j <= jb; j++)
                {
                    for (int ii = ia; ii <= ib; ii++)
                    {
                        if (Vec2d.Distance(g.CellCenter(ii, j), p.Pos) <= r) blocked.Set(g.Index(ii, j));
                    }
                }
            }
        }

        /// <summary>Neutral, unblocked, unscorched cells next to exactly one player's cells, with that player (ascending cells).</summary>
        private void FindCandidates(Simulation sim)
        {
            candidates.Clear();
            claimants.Clear();
            OwnerGrid g = sim.Grid;
            int size = g.Size;
            byte[] cells = g.Cells;
            int maxId = sim.Players.Count;
            double now = sim.TraitTime;
            for (int j = 0; j < size; j++)
            {
                int row = j * size;
                for (int i = 0; i < size; i++)
                {
                    int c = row + i;
                    if (cells[c] != OwnerGrid.Neutral) continue;
                    byte claim = 0;
                    bool contested = false;
                    if (i + 1 < size) Claim(cells[c + 1], maxId, ref claim, ref contested);
                    if (i > 0) Claim(cells[c - 1], maxId, ref claim, ref contested);
                    if (j + 1 < size) Claim(cells[c + size], maxId, ref claim, ref contested);
                    if (j > 0) Claim(cells[c - size], maxId, ref claim, ref contested);
                    if (claim == 0 || contested) continue;
                    if (blocked.Get(c) || sim.IsScorchedAt(c, now)) continue;
                    candidates.Add(c);
                    claimants.Add(claim);
                }
            }
        }

        private static void Claim(byte owner, int maxId, ref byte claim, ref bool contested)
        {
            if (owner == OwnerGrid.Neutral || owner == OwnerGrid.Void || owner > maxId) return;
            if (claim == 0) claim = owner;
            else if (claim != owner) contested = true;
        }

        /// <summary>Drops (sets to -1) every candidate on its claimant's own trail raster or 4-adjacent to it.</summary>
        private void FilterOwnTrails(Simulation sim)
        {
            OwnerGrid g = sim.Grid;
            int size = g.Size;
            IReadOnlyList<PlayerState> players = sim.Players;
            for (int i = 0; i < players.Count; i++)
            {
                PlayerState p = players[i];
                if (!p.Alive || p.Home || p.Trail.Count == 0) continue;
                bool any = false;
                for (int k = 0; k < claimants.Count && !any; k++) any = claimants[k] == p.Id;
                if (!any) continue;

                trailRaster.Clear();
                trailBand.Clear();
                IReadOnlyList<Vec2d> pts = p.Trail.Points;
                if (p.Trail.Count >= 2) GridRaster.RasterPolyline(g, pts, trailRaster);
                if (g.TryCellOf(pts[p.Trail.Count - 1], out int hi, out int hj)) trailRaster.Set(g.Index(hi, hj));
                if (g.TryCellOf(pts[0], out int si, out int sj)) trailRaster.Set(g.Index(si, sj));
                trailRaster.CopyIndices(scratch);
                for (int k = 0; k < scratch.Count; k++)
                {
                    int c = scratch[k];
                    int ci = c % size, cj = c / size;
                    trailBand.Set(c);
                    if (ci + 1 < size) trailBand.Set(c + 1);
                    if (ci > 0) trailBand.Set(c - 1);
                    if (cj + 1 < size) trailBand.Set(c + size);
                    if (cj > 0) trailBand.Set(c - size);
                }
                for (int k = 0; k < candidates.Count; k++)
                {
                    if (candidates[k] >= 0 && claimants[k] == p.Id && trailBand.Get(candidates[k])) candidates[k] = -1;
                }
            }
        }
    }
}
