// Owned by kill-core (wave D-2). docs/BIOME_TRAITS.md section 7: KillInheritance (behaviour, kill reward), P1 = Share (1.0).
using System;
using System.Collections.Generic;

namespace PainterIO.Core
{
    /// <summary>
    /// KillInheritance (Paper.io 2): when the killer of a Spark elimination is alive after the eliminating group, the
    /// victim's freed cells go to the killer instead of staying neutral. Applied by the Simulation at the end of step b
    /// (IKillTrait), so before the round end check; a dead killer (or one eliminated in the same group) gets nothing and the
    /// cells stay neutral as without the trait (ScorchedEarth then scorches them as usual). Emits TerritoryInherited
    /// (Player = killer, Other = victim, Point = the victim's head at the kill, Cells ascending, Time = the group time)
    /// right after the victim's SparkCaught and Eliminated events (Eliminated still lists every freed cell).
    /// Share &lt; 1 (tuning): the killer inherits round(Share x n) of the n freed cells, those nearest the centroid of the
    /// victim's land (squared distance in cell units, ties by ascending index), so the core of the land changes hands and
    /// the rim stays neutral; the choice depends only on the cells, so it is identical at every tick rate.
    /// Consequences (section 7.2): an inherited cell under the killer's trailing head returns it at that instant through
    /// the normal section 6 state check (an unchased return captures with its trail, a chased one captures nothing);
    /// Propagation grows the inherited land too; ScorchedEarth marks only cells that stay neutral (IsScorched needs a
    /// neutral cell).
    /// </summary>
    public sealed class KillInheritanceTrait : ISimTrait, IKillTrait
    {
        private readonly List<int> cells = new List<int>();
        private readonly List<double> keys = new List<double>();

        public TraitId Id => TraitId.KillInheritance;

        /// <summary>Share of the victim's freed cells the killer inherits (P1, in [0, 1]).</summary>
        public double Share { get; private set; } = TraitDefaults.KillInheritanceShare;

        public void Attach(Simulation sim, TraitSpec spec)
        {
            Share = spec.P1;
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
        }

        public void OnKill(Simulation sim, KillInfo kill, List<SimEvent> raised)
        {
            int[] freed = kill.FreedCells;
            if (!(Share > 0.0) || freed == null || freed.Length == 0) return;
            OwnerGrid g = sim.Grid;
            PlayerState killer = sim.Players[kill.Killer];
            if (!killer.Alive) return;

            // The freed cells that are still neutral (all of them: nothing between the elimination and this call changes
            // them; kept as a guard).
            cells.Clear();
            for (int k = 0; k < freed.Length; k++)
            {
                if (g.Cells[freed[k]] == OwnerGrid.Neutral) cells.Add(freed[k]);
            }
            if (cells.Count == 0) return;
            if (Share < 1.0) KeepNearestToCentroid(g.Size, freed);
            if (cells.Count == 0) return;

            byte id = killer.Id;
            for (int k = 0; k < cells.Count; k++) g.Set(cells[k], id);
            raised.Add(new SimEvent
            {
                Type = SimEventType.TerritoryInherited, Time = kill.Time, Player = kill.Killer, Other = kill.Victim, Point = kill.Point,
                Cells = cells.ToArray(),
            });
        }

        /// <summary>Keeps round(Share x n) cells of 'cells' (ascending result): the nearest to the centroid of 'land'.</summary>
        private void KeepNearestToCentroid(int size, int[] land)
        {
            int keep = (int)Math.Floor(Share * cells.Count + 0.5);
            if (keep >= cells.Count) return;
            if (keep <= 0)
            {
                cells.Clear();
                return;
            }
            double si = 0.0, sj = 0.0;
            for (int k = 0; k < land.Length; k++)
            {
                si += land[k] % size;
                sj += land[k] / size;
            }
            double ci = si / land.Length, cj = sj / land.Length;
            keys.Clear();
            var order = new int[cells.Count];
            for (int k = 0; k < cells.Count; k++)
            {
                double di = cells[k] % size - ci, dj = cells[k] / size - cj;
                keys.Add(di * di + dj * dj);
                order[k] = k;
            }
            // A total order (distance, then cell index), so the unstable sort is deterministic.
            Array.Sort(order, (a, b) =>
            {
                int c = keys[a].CompareTo(keys[b]);
                return c != 0 ? c : cells[a].CompareTo(cells[b]);
            });
            var chosen = new int[keep];
            for (int k = 0; k < keep; k++) chosen[k] = cells[order[k]];
            Array.Sort(chosen);
            cells.Clear();
            cells.AddRange(chosen);
        }
    }
}
