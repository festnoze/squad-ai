using System;

namespace PainterIO.Core
{
    /// <summary>
    /// Rule v1.5 (contract 29): what becomes of the pieces of a living player's territory that a transfer cut off from the
    /// piece it keeps (SimConfig.SeveredTerritory).
    /// </summary>
    public enum SeveredTerritoryRule
    {
        /// <summary>The pre-v1.5 behaviour: the victim keeps every piece (bit-identical to the simulation before v1.5).</summary>
        Off = 0,
        /// <summary>The severed pieces become neutral (plain neutral, never scorched). The default.</summary>
        Neutral = 1,
        /// <summary>The severed pieces go to the player whose capture made the cut.</summary>
        Capturer = 2,
    }

    /// <summary>
    /// Rule v1.6 (contract 30, designer request "your domain must be one single domain"): what KillInheritance does when the
    /// inherited land does not touch the killer's domain (SimConfig.InheritanceBridge). Only read when KillInheritance is
    /// enabled with Share &gt; 0: classic rounds and the other trait sets never look at it.
    /// </summary>
    public enum InheritanceBridgeRule
    {
        /// <summary>The pre-v1.6 behaviour: the inherited land stays an island (bit-identical to the simulation before v1.6).</summary>
        Off = 0,
        /// <summary>
        /// Single domain with a bridge (the default): the line of the kill (the killer's trail from its exit to the cut point
        /// and the victim's trail from the cut point back to its land) becomes a band of territory that joins the inherited
        /// land; whatever still stays apart is severed (neutral). Closures that would leave a detached part also take their
        /// trail footprint.
        /// </summary>
        Bridge = 1,
        /// <summary>Single domain without the band: the killer keeps its anchor piece, inherited land apart from it is neutral.</summary>
        AnchorOnly = 2,
    }

    /// <summary>
    /// Rule v1.8 (contract 32, designer request "the domain must always stay contiguous"): whether the single-domain
    /// guarantee of rule v1.6 holds in every round type (SimConfig.SingleDomain).
    /// </summary>
    public enum SingleDomainRule
    {
        /// <summary>
        /// The pre-v1.8 behaviour, bit-identical: the single-domain machinery runs only on the KillInheritance path (rule
        /// v1.6, SimConfig.InheritanceBridge); classic, Liquide and Electricite rounds have no guarantee.
        /// </summary>
        Off = 0,
        /// <summary>
        /// The default: in every round type every living player's territory stays one 8-connected domain. A return whose
        /// capture would leave the domain in pieces (a detached lasso pocket or region, a trail that joins two separate
        /// pieces) takes the band of its trail; whatever an own or simultaneous action still leaves apart is severed.
        /// </summary>
        On = 1,
    }

    /// <summary>
    /// Rule v1.9 (contract 33, designer request "border ride"): whether a head that runs along the arena boundary for more
    /// than SimConfig.BorderRideDelay seconds rides it at SimConfig.BorderRideFactor times its speed (SimConfig.BorderRide).
    /// </summary>
    public enum BorderRideRule
    {
        /// <summary>The pre-v1.9 behaviour, bit-identical (the Core default, so every pinned hash keeps its value).</summary>
        Off = 0,
        /// <summary>The border ride is on (the game turns it on for real rounds: GameSession.RoundConfig).</summary>
        On = 1,
    }

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

        /// <summary>
        /// Rule v1.7 (contract 31): the conquest goal as a share of the conquerable cells (Simulation.ConquestCellCount).
        /// A player owning Conquest.TargetCells of them ends the round at once and wins (RoundEndReason.Conquest). 1.0 (the
        /// default) is the goal the HUD shows as 100 %; values above 1 count as 1; 0 or less turns the goal off.
        /// </summary>
        public double ConquestShare = Conquest.DefaultShare;

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

        /// <summary>
        /// Rule v1.5 (contract 29, designer request "la partie dans laquelle l'ennemi n'est pas ne lui appartient plus"): when
        /// a capture cuts a living rival's territory into separate pieces, the rival keeps only the piece where it is (its
        /// pawn's cell, or the cell it left home from while trailing; the largest piece when that cell is not in one) and
        /// the other pieces of that split become neutral (Neutral, the default) or the cutter's (Capturer). Off restores
        /// the pre-v1.5 behaviour exactly. A core rule, not a biome trait: "Regles classiques" keep it.
        /// </summary>
        public SeveredTerritoryRule SeveredTerritory = SeveredTerritoryRule.Neutral;

        /// <summary>
        /// Rule v1.6 (contract 30, KillInheritance path only): Bridge (default) keeps every living player's territory one
        /// 8-connected domain in rounds with KillInheritance (Share &gt; 0) and joins the inherited land with the band of
        /// the kill line; AnchorOnly keeps one domain without the band; Off restores the pre-v1.6 behaviour exactly.
        /// Ignored (and never read) without KillInheritance, so classic rounds and the other trait sets are unchanged.
        /// </summary>
        public InheritanceBridgeRule InheritanceBridge = InheritanceBridgeRule.Bridge;

        /// <summary>
        /// Rule v1.6: half width (u) of the bridge band: every cell whose center lies within this distance of the kill line
        /// becomes the killer's, plus the supercover raster of the line itself (the footprint a closure gives a trail), so
        /// the band is never thinner than one cell. Default TraitDefaults.KillInheritanceBandHalfWidth (0.45 u = HeadRadius:
        /// a band as wide as the pearl, about 7 cells).
        /// </summary>
        public double InheritanceBandHalfWidth = TraitDefaults.KillInheritanceBandHalfWidth;

        /// <summary>
        /// Rule v1.8 (contract 32): On (default) keeps every living player's territory one 8-connected domain in every
        /// round type (classic and every trait set): a return whose capture would leave the domain in pieces takes the band
        /// of its trail (half width InheritanceBandHalfWidth plus the supercover raster of the trail), so the pieces become
        /// one domain; an own or simultaneous action that still leaves a part apart keeps the piece of the return cell and
        /// severs the rest (neutral). Enemy-caused splits keep rule v1.5 (SeveredTerritory). With KillInheritance the v1.6
        /// bridge applies (InheritanceBridge Off then behaves as AnchorOnly). Off restores the pre-v1.8 behaviour exactly
        /// (the guarantee only on the KillInheritance path). Not hashed.
        /// </summary>
        public SingleDomainRule SingleDomain = SingleDomainRule.On;

        /// <summary>
        /// Rule v1.9 (contract 33): border ride switch. Off (the Core default) is bit-identical to the simulation before
        /// v1.9; the game sets On in GameSession.RoundConfig.
        /// </summary>
        public BorderRideRule BorderRide = BorderRideRule.Off;

        /// <summary>Rule v1.9: speed factor of a riding head (a factor of the tick speed product, like Conduction).</summary>
        public double BorderRideFactor = 3.0;

        /// <summary>Rule v1.9: seconds of continuous contact with the boundary (sim time) before the ride starts.</summary>
        public double BorderRideDelay = 1.0;

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
