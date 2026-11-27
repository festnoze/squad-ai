using System;

namespace PainterIO.Core
{
    /// <summary>
    /// Mutable per-round configuration (contract 3.2): one public field per Tuning entry, same name, initialized from
    /// Tuning, plus the seed. A Simulation reads only its SimConfig, never Tuning directly, so tests and the runtime
    /// test settings can change any value.
    /// </summary>
    public sealed class SimConfig
    {
        public ulong Seed = 1;

        // Arena (R1).
        public double ArenaHalfSize = Tuning.ArenaHalfSize;
        public double ArenaCornerRadius = Tuning.ArenaCornerRadius;
        public double ArenaMargin = Tuning.ArenaMargin;
        public double CellSize = Tuning.CellSize;
        public ArenaPolygon ArenaBoundary;

        // Players and start (R2).
        public int PlayerCount = Tuning.PlayerCount;
        public double StartDiscRadius = Tuning.StartDiscRadius;
        public double StartDiscOffset = Tuning.StartDiscOffset;

        // Motion (R3, R4).
        public double PawnSpeed = Tuning.PawnSpeed;
        public double TurnRateDeg = Tuning.TurnRateDeg;
        public double BorderHoldAngleDeg = Tuning.BorderHoldAngleDeg;

        // Contacts and La Revanche (R10 to R13).
        public double HeadRadius = Tuning.HeadRadius;
        public double TrailHalfWidth = Tuning.TrailHalfWidth;
        public double HeadGrace = Tuning.HeadGrace;
        public double SparkSpeedFactor = Tuning.SparkSpeedFactor;

        // Round (R19).
        public double RoundDuration = Tuning.RoundDuration;

        // Le Lasso (R15 to R17).
        public bool LassoEnabled = Tuning.LassoEnabled;
        public double LassoFirstSpawn = Tuning.LassoFirstSpawn;
        public double LassoRespawn = Tuning.LassoRespawn;
        public double RingRadius = Tuning.RingRadius;
        public double RingMinHeadDistance = Tuning.RingMinHeadDistance;
        public double RingClearance = Tuning.RingClearance;
        public double LassoMinArc = Tuning.LassoMinArc;
        public double LassoMinArea = Tuning.LassoMinArea;

        // Event engine (section 6).
        public int TickRate = Tuning.TickRate;
        public double EventEpsilonSeconds = Tuning.EventEpsilonSeconds;
        public int MaxEventsPerTick = Tuning.MaxEventsPerTick;

        // Bots (section 9).
        public int BotCount = Tuning.BotCount;

        // Biome traits (docs/BIOME_TRAITS.md section 4, contract 27).

        /// <summary>
        /// The trait set of the round. The Simulation applies its config traits to its cloned config (so the caller's
        /// object keeps its values) and attaches its behaviour traits. Classic (the default, or null) = no trait, the
        /// simulation is bit-identical to the one without traits.
        /// </summary>
        public RuleTraits Traits = RuleTraits.Classic;

        /// <summary>Cut contact radius multiplier (ArcReach): ContactRadius = (HeadRadius + TrailHalfWidth) x ContactScale.</summary>
        public double ContactScale = 1.0;

        /// <summary>
        /// docs/BIOME_TRAITS.md 7.1 (kill-core, api addition): true (the default) = a spark runs at SparkSpeedFactor x
        /// PawnSpeed x the victim's SpeedMultiplier at the cut, so the brief's "1.8 fois la vitesse du pion" stays true with
        /// speed bonuses; false = always SparkSpeedFactor x PawnSpeed (a boosted player escapes more easily). Irrelevant
        /// while every SpeedMultiplier is 1 (classic rounds, rounds without KillSpeedBoost).
        /// </summary>
        public bool SparkFollowsVictimSpeed = true;

        /// <summary>Tick duration in seconds.</summary>
        public double Dt => 1.0 / TickRate;

        /// <summary>
        /// Base spark speed in u/s (R12): SparkSpeedFactor x PawnSpeed (the BASE pawn speed, never a trait factor). The speed
        /// of an actual spark is Spark.Speed = SparkSpeedOf(victim.SpeedMultiplier), equal to this in classic rounds.
        /// </summary>
        public double SparkSpeed => SparkSpeedFactor * PawnSpeed;

        /// <summary>
        /// Speed of a spark spawned on a victim with this SpeedMultiplier (docs/BIOME_TRAITS.md 7.1, api addition):
        /// SparkSpeed x victimSpeedMultiplier when SparkFollowsVictimSpeed, else SparkSpeed. Exactly SparkSpeed for 1.0.
        /// </summary>
        public double SparkSpeedOf(double victimSpeedMultiplier)
        {
            return SparkFollowsVictimSpeed ? SparkSpeed * victimSpeedMultiplier : SparkSpeed;
        }

        /// <summary>Cut contact distance (R10): (HeadRadius + TrailHalfWidth) x ContactScale (x 1.0 is exact: classic unchanged).</summary>
        public double ContactRadius => (HeadRadius + TrailHalfWidth) * ContactScale;

        /// <summary>Ring pickup distance (R15): HeadRadius + RingRadius.</summary>
        public double PickupRadius => HeadRadius + RingRadius;

        /// <summary>Max heading change in radians per second (R3); 0 means instant turns.</summary>
        public double TurnRateRad => TurnRateDeg * (Math.PI / 180.0);

        /// <summary>BorderHoldAngleDeg in radians, the holdAngleRad argument of Arena.Step (R4).</summary>
        public double BorderHoldAngleRad => BorderHoldAngleDeg * (Math.PI / 180.0);

        /// <summary>Ownership grid side in cells: round(2 ArenaHalfSize / CellSize) = 512 by default (contract 3.1).</summary>
        public int GridSize => (int)Math.Round(2.0 * ArenaHalfSize / CellSize);

        /// <summary>Field-by-field copy; Traits is deep-copied (RuleTraits.Clone), null becomes Classic.</summary>
        public SimConfig Clone()
        {
            var copy = (SimConfig)MemberwiseClone();
            copy.Traits = Traits == null ? RuleTraits.Classic : Traits.Clone();
            return copy;
        }
    }
}
