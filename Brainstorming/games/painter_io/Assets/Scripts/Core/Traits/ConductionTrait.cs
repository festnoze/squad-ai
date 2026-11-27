// Owned by traits-core (wave D-1). docs/BIOME_TRAITS.md section 2: Conduction (behaviour), P1 = HomeSpeedFactor (1.30).
using System.Collections.Generic;

namespace PainterIO.Core
{
    /// <summary>
    /// Conduction: a player whose current cell is its own at tick start moves at PawnSpeed x HomeSpeedFactor for that
    /// whole tick (section 6 step 1), even if it exits during the tick. The spark speed stays SparkSpeedFactor x the BASE
    /// PawnSpeed. Tick-rate dependent by design, like turning (the factor applies per whole tick): no cross-rate test.
    /// </summary>
    public sealed class ConductionTrait : ISimTrait, ISpeedTrait
    {
        public TraitId Id => TraitId.Conduction;

        /// <summary>The speed factor on own territory (P1).</summary>
        public double HomeSpeedFactor { get; private set; } = TraitDefaults.ConductionHomeSpeedFactor;

        /// <summary>The largest factor SpeedFactor can return (HeadGrace check): max(1, HomeSpeedFactor).</summary>
        public double MaxSpeedFactor => HomeSpeedFactor > 1.0 ? HomeSpeedFactor : 1.0;

        public void Attach(Simulation sim, TraitSpec spec)
        {
            HomeSpeedFactor = spec.P1;
        }

        public double SpeedFactor(Simulation sim, PlayerState p)
        {
            return sim.Grid.Cells[p.Cell] == p.Id ? HomeSpeedFactor : 1.0;
        }

        public void AugmentCapture(Simulation sim, PlayerState p, List<int> cells)
        {
        }

        public void OnEliminated(Simulation sim, PlayerState p, int[] freedCells, double time)
        {
        }

        public void EndOfTick(Simulation sim, List<SimEvent> raised)
        {
        }

        /// <summary>
        /// The factor a player gets on its own territory under these traits (1.0 without Conduction). Bots read it from
        /// SimConfig.Traits to estimate travel times on their own land (docs/BIOME_TRAITS.md section 4).
        /// </summary>
        public static double HomeSpeedFactorOf(RuleTraits traits)
        {
            TraitSpec spec = traits?.Get(TraitId.Conduction);
            return spec != null ? spec.P1 : 1.0;
        }
    }
}
