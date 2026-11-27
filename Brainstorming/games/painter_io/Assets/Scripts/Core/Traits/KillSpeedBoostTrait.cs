// Owned by kill-core (wave D-2). docs/BIOME_TRAITS.md section 7: KillSpeedBoost (behaviour, kill reward), P1 = PerKill
// (0.10), P2 = Cap (0.30).
using System;
using System.Collections.Generic;

namespace PainterIO.Core
{
    /// <summary>
    /// KillSpeedBoost (Paper.io 4): each kill adds PerKill to the killer's permanent PlayerState.SpeedMultiplier for the
    /// rest of the round, capped at 1 + Cap (applied by the Simulation at the end of step b, killer alive only). The tick
    /// speed (section 6 step 1) is PawnSpeed x SpeedMultiplier x the Conduction factor when home, read at tick start, so a
    /// boost gained during a tick applies from the next tick: like Conduction and turning, the trait is tick-rate dependent
    /// by design (no cross-rate test). Emits SpeedBoosted (Player = killer, Other = victim, Value = the new multiplier)
    /// only when the multiplier actually grows (nothing at the cap). Section 7.1: a spark spawned later on this player runs
    /// at SparkSpeedFactor x PawnSpeed x its multiplier (SimConfig.SparkFollowsVictimSpeed), so a boosted player stays
    /// catchable at the same ratio; a boost gained during a chase does not change the running spark. The HeadGrace check
    /// uses the maximum reachable speed (MaxSpeedFactor = 1 + Cap, multiplied with Conduction's maximum).
    /// </summary>
    public sealed class KillSpeedBoostTrait : ISimTrait, IKillTrait, ISpeedTrait
    {
        public TraitId Id => TraitId.KillSpeedBoost;

        /// <summary>Added to the multiplier per kill (P1).</summary>
        public double PerKill { get; private set; } = TraitDefaults.KillSpeedBoostPerKill;

        /// <summary>The multiplier never exceeds 1 + Cap (P2).</summary>
        public double Cap { get; private set; } = TraitDefaults.KillSpeedBoostCap;

        /// <summary>The largest multiplier a player can reach (HeadGrace check): 1 + Cap.</summary>
        public double MaxSpeedFactor => 1.0 + Math.Max(0.0, Cap);

        public void Attach(Simulation sim, TraitSpec spec)
        {
            PerKill = spec.P1;
            Cap = spec.P2;
        }

        /// <summary>1.0: the boost lives in PlayerState.SpeedMultiplier, which the Simulation applies itself (7.1).</summary>
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
            if (!(PerKill > 0.0)) return;
            PlayerState killer = sim.Players[kill.Killer];
            if (!killer.Alive) return;
            double next = Math.Min(MaxSpeedFactor, killer.SpeedMultiplier + PerKill);
            if (!(next > killer.SpeedMultiplier)) return;
            killer.SpeedMultiplier = next;
            raised.Add(new SimEvent
            {
                Type = SimEventType.SpeedBoosted, Time = kill.Time, Player = kill.Killer, Other = kill.Victim, Point = kill.Point, Value = next,
            });
        }
    }
}
