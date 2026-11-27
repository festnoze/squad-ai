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
                                      // cells (all ascending)
        public bool Chased;           // Return: the exit was cut (PlayerState.ExitWasCut, docs/BIOME_TRAITS.md 7.1; classic:
                                      // the player had a spark at the return instant): saved, captures nothing.
                                      // ShieldStarted: the shield extinguished a spark on the killer's trail
        public double Margin;         // Return while chased: (L - S) / Spark.Speed at the return instant; 0 when not chased
                                      // or when the spark was already extinguished (KillShield)
        public double DistanceHome;   // SparkCaught: distance to nearest own cell computed BEFORE Neutralize (u), or -1
        public EliminationCause Cause;
        public double Value;          // api addition (docs/BIOME_TRAITS.md section 7): SpeedBoosted: the new SpeedMultiplier;
                                      // ShieldStarted / ShieldEnded: the shield end time. Otherwise 0

        public override string ToString()
        {
            return Type + " t=" + Time.ToString("R", System.Globalization.CultureInfo.InvariantCulture)
                   + " player=" + Player + " other=" + Other + (Cause != EliminationCause.None ? " cause=" + Cause : "");
        }
    }
}
