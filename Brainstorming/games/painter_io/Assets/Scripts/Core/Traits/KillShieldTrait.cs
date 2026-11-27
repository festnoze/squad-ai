// Owned by kill-core (wave D-2). docs/BIOME_TRAITS.md section 7: KillShield (behaviour, kill reward), P1 = Duration (3.0 s).
using System.Collections.Generic;

namespace PainterIO.Core
{
    /// <summary>
    /// KillShield: after a kill, the killer (alive after the group) is invincible until t_kill + Duration: enemy heads
    /// cannot cut its trail (the Simulation computes no Cut candidate on a shielded trail and re-checks it when applying a
    /// cut), and a spark already on its trail is extinguished at the kill instant. Its loop stays lost (PlayerState.
    /// ExitWasCut stays set: the return captures nothing, Return.Chased = true). Territory loss to 0 cells still eliminates.
    /// A second kill during the shield extends it to the new t_kill + Duration. The shield ends exactly at its end time
    /// through the ShieldEnd candidate of section 6 (the Simulation emits ShieldEnded); after that the player is
    /// vulnerable again under the normal rules (a cut on a still running, already cut exit spawns a new spark).
    /// Emits ShieldStarted (Player = killer, Other = victim, Value = the end time, Chased = a spark was extinguished)
    /// whenever the end time grows. Duration 0 does nothing (no shield, no extinguished spark). The timing depends only on
    /// the kill instant, so it is identical at every tick rate.
    /// </summary>
    public sealed class KillShieldTrait : ISimTrait, IKillTrait
    {
        public TraitId Id => TraitId.KillShield;

        /// <summary>Seconds of invincibility after a kill (P1).</summary>
        public double Duration { get; private set; } = TraitDefaults.KillShieldDuration;

        public void Attach(Simulation sim, TraitSpec spec)
        {
            Duration = spec.P1;
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
            if (!(Duration > 0.0)) return;
            PlayerState killer = sim.Players[kill.Killer];
            if (!killer.Alive) return;
            double end = kill.Time + Duration;
            bool extinguished = killer.Spark != null;
            killer.Spark = null;   // ExitWasCut stays: the cut exit still captures nothing (7.1)
            if (!(end > killer.ShieldEnd) && !extinguished) return;
            if (end > killer.ShieldEnd) killer.ShieldEnd = end;
            raised.Add(new SimEvent
            {
                Type = SimEventType.ShieldStarted, Time = kill.Time, Player = kill.Killer, Other = kill.Victim, Point = kill.Point,
                Value = killer.ShieldEnd, Chased = extinguished,
            });
        }
    }
}
