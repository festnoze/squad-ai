// Owned by A4 (sim). Contract 5.5.
using System;

namespace PainterIO.Core
{
    /// <summary>
    /// Read-only facade handed to controllers and views. It returns the live objects (no copies): controllers must never
    /// mutate anything reachable from it (contract 5.5).
    /// </summary>
    public sealed class SimView
    {
        private readonly Simulation sim;

        public SimView(Simulation sim)
        {
            this.sim = sim ?? throw new ArgumentNullException(nameof(sim));
        }

        public double Time => sim.Time;
        public SimConfig Config => sim.Config;
        public Arena Arena => sim.Arena;
        public OwnerGrid Grid => sim.Grid;
        public int PlayerCount => sim.Players.Count;
        public PlayerState Player(int index) => sim.Players[index];
        public Ring Ring => sim.Ring;

        /// <summary>The round's trait set (docs/BIOME_TRAITS.md section 4): Config.Traits, Classic when none.</summary>
        public RuleTraits Traits => sim.Config.Traits;

        /// <summary>
        /// ScorchedEarth: the cell is neutral and still scorched now (Time &lt; EliminatedAt + Duration). Always false
        /// without the trait.
        /// </summary>
        public bool IsScorched(int cell) => sim.IsScorchedAt(cell, sim.Time);

        /// <summary>
        /// ScorchedEarth (api addition, for the fade of _PIO_ScorchMask): the time the cell's latest scorch ends, or
        /// -infinity when it was never scorched (or without the trait). Not filtered by owner or time: combine with
        /// IsScorched.
        /// </summary>
        public double ScorchEndTime(int cell) => sim.Scorch != null ? sim.Scorch.EndTime(cell) : double.NegativeInfinity;

        /// <summary>
        /// Speed a player gets on its own territory (api addition): PawnSpeed x the Conduction factor (PawnSpeed without
        /// Conduction). Off its territory a player always moves at PawnSpeed.
        /// </summary>
        public double HomeSpeed => sim.Config.PawnSpeed * ConductionTrait.HomeSpeedFactorOf(sim.Config.Traits);

        /// <summary>
        /// Rule v1.6 (contract 30, api addition): true when the round keeps every living player's territory one domain
        /// (KillInheritance with Share &gt; 0 and SimConfig.InheritanceBridge not Off). Rule v1.8 (contract 32): also true
        /// in every round type when SimConfig.SingleDomain is On (the default); false in classic rounds only with Off.
        /// </summary>
        public bool SingleDomain => sim.SingleDomain;

        // ------------------------------------------------------------------------------------------------------------
        // Kill rewards (docs/BIOME_TRAITS.md section 7, api additions, kill-core wave D-2).

        /// <summary>
        /// The player's permanent speed multiplier (1.0 unless KillSpeedBoost raised it). The tick speed is PawnSpeed x
        /// SpeedMultiplier x (Conduction factor when home).
        /// </summary>
        public double SpeedMultiplier(int index) => sim.Players[index].SpeedMultiplier;

        /// <summary>
        /// Speed the player moves at in its next tick if its current cell stays the same: PawnSpeed x SpeedMultiplier x
        /// (the Conduction factor when home). 0 for an eliminated player.
        /// </summary>
        public double EffectiveSpeed(int index)
        {
            PlayerState p = sim.Players[index];
            if (!p.Alive) return 0.0;
            double speed = sim.Config.PawnSpeed * p.SpeedMultiplier;
            if (p.BorderRiding) speed *= sim.Config.BorderRideFactor;   // rule v1.9 (contract 33)
            return p.Home ? speed * ConductionTrait.HomeSpeedFactorOf(sim.Config.Traits) : speed;
        }

        /// <summary>
        /// Rule v1.9 (contract 33, api addition): true while the player is alive and rides the arena boundary (speed x
        /// SimConfig.BorderRideFactor, heading = the boundary tangent). Always false with SimConfig.BorderRide Off.
        /// </summary>
        public bool IsBorderRiding(int index)
        {
            PlayerState p = sim.Players[index];
            return p.Alive && p.BorderRiding;
        }

        /// <summary>Rule v1.9: the sim time the player's current ride started (NaN when it is not riding).</summary>
        public double BorderRideStartTime(int index)
        {
            PlayerState p = sim.Players[index];
            return p.Alive && p.BorderRiding ? p.BorderRideStart : double.NaN;
        }

        /// <summary>KillShield: true while the player is alive and shielded (enemy heads cannot cut its trail).</summary>
        public bool IsShielded(int index)
        {
            PlayerState p = sim.Players[index];
            return p.Alive && p.Shielded;
        }

        /// <summary>
        /// KillShield: the time the current shield ends (t_kill + Duration of the latest kill), or double.NegativeInfinity
        /// when the player is not shielded. The ShieldEnded event fires exactly at that time.
        /// </summary>
        public double ShieldEndTime(int index)
        {
            PlayerState p = sim.Players[index];
            return p.Alive && p.Shielded ? p.ShieldEnd : double.NegativeInfinity;
        }

        /// <summary>
        /// Seconds until the spark reaches the head if the head keeps moving at its trailing speed (R12/R13 closed form):
        /// (L - S) / (Spark.Speed - PawnSpeed x SpeedMultiplier), clamped at 0 (docs/BIOME_TRAITS.md 7.1: the spark speed is
        /// fixed at the cut; classic: (L - S) / (SparkSpeed - PawnSpeed)). +inf when the player has no spark (or is
        /// eliminated), or when the spark is not faster than the pawn. Rule v1.9: a chased player never rides the border
        /// (the ride ends when the spark appears), so the border ride factor never enters this closed form.
        /// </summary>
        public double SparkCatchEta(int index)
        {
            PlayerState p = sim.Players[index];
            if (!p.Alive || p.Spark == null) return double.PositiveInfinity;
            SimConfig c = sim.Config;
            double sparkSpeed = p.Spark.Speed > 0.0 ? p.Spark.Speed : c.SparkSpeed;
            double closing = sparkSpeed - c.PawnSpeed * p.SpeedMultiplier;
            if (!(closing > 0.0)) return double.PositiveInfinity;
            double gap = p.Trail.Length - p.Spark.S;
            return gap > 0.0 ? gap / closing : 0.0;
        }
    }
}
