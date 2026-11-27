// Owned by traits-core (wave D-1). docs/BIOME_TRAITS.md section 2: ScorchedEarth (behaviour), P1 = Duration (15 s).
using System.Collections.Generic;

namespace PainterIO.Core
{
    /// <summary>
    /// ScorchedEarth: when a player is eliminated, its freed cells become scorched until EliminatedAt + Duration. A
    /// scorched cell is still neutral and capturable normally (captures ignore the scorch), but Propagation and
    /// Coalescence never fill it. A scorched cell that changes owner is no longer scorched (IsScorched requires a neutral
    /// cell); a later elimination that frees it again scorches it anew. Emits nothing (Eliminated already carries the
    /// cells); SimView.IsScorched / ScorchEndTime expose the state to views.
    /// </summary>
    public sealed class ScorchedEarthTrait : ISimTrait
    {
        /// <summary>One elimination's scorch (for the state hash).</summary>
        internal struct Batch
        {
            public double Until;
            public int Count;
        }

        private Simulation sim;
        private double[] until;                     // per cell: scorch end time, 0 = never scorched (lazy, grid size)
        private readonly List<Batch> batches = new List<Batch>();

        public TraitId Id => TraitId.ScorchedEarth;

        /// <summary>Seconds a freed cell stays scorched (P1).</summary>
        public double Duration { get; private set; } = TraitDefaults.ScorchedEarthDuration;

        public void Attach(Simulation sim, TraitSpec spec)
        {
            this.sim = sim;
            Duration = spec.P1;
            sim.Scorch = this;
        }

        public double SpeedFactor(Simulation sim, PlayerState p) => 1.0;

        public void AugmentCapture(Simulation sim, PlayerState p, List<int> cells)
        {
        }

        public void OnEliminated(Simulation sim, PlayerState p, int[] freedCells, double time)
        {
            if (!(Duration > 0.0) || freedCells == null || freedCells.Length == 0) return;
            double end = time + Duration;
            if (until == null) until = new double[sim.Grid.Cells.Length];
            for (int k = 0; k < freedCells.Length; k++)
            {
                int c = freedCells[k];
                if (end > until[c]) until[c] = end;
            }
            batches.Add(new Batch { Until = end, Count = freedCells.Length });
        }

        public void EndOfTick(Simulation sim, List<SimEvent> raised)
        {
            // Forget expired batches (they no longer belong to the state hash).
            double now = sim.Time;
            for (int k = batches.Count - 1; k >= 0; k--)
            {
                if (!(now < batches[k].Until)) batches.RemoveAt(k);
            }
        }

        /// <summary>
        /// Rule v1.5 (contract 29, api addition): forgets the cell's scorch, so a cell that changed owner after its scorch
        /// started and is made neutral again by a split (TerritorySevered) is plain neutral, not scorched again. The state
        /// hash (batches) is unchanged.
        /// </summary>
        internal void Forget(int cell)
        {
            if (until != null) until[cell] = 0.0;
        }

        /// <summary>True when the cell is neutral and its scorch has not ended at 'now' (now &lt; EliminatedAt + Duration).</summary>
        public bool IsScorched(int cell, double now)
        {
            return until != null && now < until[cell] && sim.Grid.Cells[cell] == OwnerGrid.Neutral;
        }

        /// <summary>
        /// The time the cell's latest scorch ends (EliminatedAt + Duration), or -infinity when it was never scorched. Not
        /// filtered by ownership or time: views combine it with IsScorched for the fade of the last seconds.
        /// </summary>
        public double EndTime(int cell)
        {
            return until != null && until[cell] > 0.0 ? until[cell] : double.NegativeInfinity;
        }

        /// <summary>Scorch batches not yet expired at 'now', in elimination order (state hash).</summary>
        internal void CopyActive(double now, List<Batch> output)
        {
            output.Clear();
            for (int k = 0; k < batches.Count; k++)
            {
                if (now < batches[k].Until) output.Add(batches[k]);
            }
        }
    }
}
