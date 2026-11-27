// Written by A1 as complete data types (contract 5.5), owned by A4.
namespace PainterIO.Core
{
    public enum EliminationCause { None = 0, Spark = 1, TerritoryLost = 2 }

    public enum SimEventType
    {
        Exit, Return, Cut, SparkCaught, Eliminated, TerritoryStolen, LassoPocket,
        LassoCrossNoCharge, RingSpawned, RingPicked, RoundEnded,
        TerritoryGrew,   // docs/BIOME_TRAITS.md section 4, appended at the END: Propagation growth (Player, Cells, tick end time)

        // docs/BIOME_TRAITS.md section 7 (kill rewards), appended at the END. Time = the kill's group time, except
        // ShieldEnded (the exact shield end instant). Point = the victim's head at the kill (SparkCaught.Point), except
        // ShieldEnded (unset).
        TerritoryInherited,   // KillInheritance: Player = killer, Other = victim, Point = the victim's head, Cells = inherited
        SpeedBoosted,         // KillSpeedBoost: Player = killer, Other = victim, Value = the new SpeedMultiplier
        ShieldStarted,        // KillShield: Player = killer, Other = victim, Value = the shield end time, Chased = a spark
                              // on the killer's trail was extinguished (its loop stays lost: ExitWasCut)
        ShieldEnded,          // KillShield: Player, Value = the end time (= Time)

        // Rule v1.5 (contract 29), appended at the END. Raised in section 6 step a right after the Return events of the
        // group whose captures cut the territory: Player = the victim, Other = the cutter (the lowest-index returner that
        // took cells of the split territory), Recipient = the player that received the severed cells (Other with
        // SeveredTerritoryRule.Capturer) or -1 when they became neutral, Cells = the severed cells (ascending).
        TerritorySevered,

        // Rule v1.6 (contract 30, KillInheritance bridge), appended at the END. Raised in section 6 step b right after the
        // kill rewards of a kill (TerritoryInherited first) when the inherited land was joined to the killer's domain by
        // the bridge band: Player = the killer, Other = the victim, Point = the victim's head at the kill (as
        // TerritoryInherited), Cells = the band cells that became the killer's (ascending; cells it already owned are not
        // listed). The single-domain rule severs whatever stays apart with TerritorySevered (Other = -1, Recipient = -1).
        InheritanceBridged,
    }

    /// <summary>One resolved event of a Step (section 6), raised in resolution order.</summary>
    public sealed class SimEvent
    {
        public SimEventType Type;
        public double Time;           // the group time of section 6
        public int Player = -1;
        public int Other = -1;        // Cut: the attacker (R11). SparkCaught, and Eliminated with Cause Spark: Spark.Attacker.
                                      // TerritoryStolen, and Eliminated with Cause TerritoryLost: the returning player that
                                      // took the cell (lowest index if several). Otherwise -1.
        public Vec2d Point;           // Cut: PointAt(s_cut). Exit / Return: crossing point. LassoPocket / LassoCrossNoCharge: X.
                                      // SparkCaught: head.
        public double S;              // Cut: s_cut
        public int[] Cells;           // Return: captured (applied) cells, always empty when Chased (contract 24, R13 v1.4);
                                      // Eliminated: freed cells; LassoPocket: pocket cells added; TerritoryGrew: grown
                                      // cells; TerritorySevered: severed cells; InheritanceBridged: band cells (all
                                      // ascending)
        public bool Chased;           // Return: the exit was cut (PlayerState.ExitWasCut, docs/BIOME_TRAITS.md 7.1; classic:
                                      // the player had a spark at the return instant): saved, captures nothing.
                                      // ShieldStarted: the shield extinguished a spark on the killer's trail
        public double Margin;         // Return while chased: (L - S) / Spark.Speed at the return instant; 0 when not chased
                                      // or when the spark was already extinguished (KillShield)
        public double DistanceHome;   // SparkCaught: distance to nearest own cell computed BEFORE Neutralize (u), or -1
        public EliminationCause Cause;
        public double Value;          // api addition (docs/BIOME_TRAITS.md section 7): SpeedBoosted: the new SpeedMultiplier;
                                      // ShieldStarted / ShieldEnded: the shield end time. Otherwise 0
        public int Recipient = -1;    // api addition (rule v1.5, contract 29): TerritorySevered: the player index that
                                      // received the severed cells, -1 when they became neutral. Otherwise -1

        public override string ToString()
        {
            return Type + " t=" + Time.ToString("R", System.Globalization.CultureInfo.InvariantCulture)
                   + " player=" + Player + " other=" + Other + (Cause != EliminationCause.None ? " cause=" + Cause : "");
        }
    }
}
