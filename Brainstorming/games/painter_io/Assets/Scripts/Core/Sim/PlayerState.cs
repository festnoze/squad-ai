// Written by A1 as complete data types (contract 5.5), owned by A4.
namespace PainterIO.Core
{
    /// <summary>La Revanche chase state of one exit (R11, R12). S is always the closed form, never accumulated.</summary>
    public sealed class Spark
    {
        public double SCut;
        public double TimeCut;
        public int Attacker;
        public double S;          // closed form SCut + Speed (Time - TimeCut) at the end of the last tick
        public double PrevS;      // S at the start of the last tick (SCut when spawned during it); render interpolation

        /// <summary>
        /// Spark speed in u/s, fixed at spawn (docs/BIOME_TRAITS.md 7.1, api addition): SimConfig.SparkSpeedOf(the victim's
        /// SpeedMultiplier at the cut) = SparkSpeedFactor x PawnSpeed x victim.SpeedMultiplier when SparkFollowsVictimSpeed
        /// (the default), else SparkSpeedFactor x PawnSpeed. Conduction never counts (a chased player is off its land).
        /// Every closed form (R12, R13, section 6) uses it; a boost gained during the chase leaves it unchanged. Classic:
        /// exactly SimConfig.SparkSpeed. 0 (a Spark built outside the Core) means SimConfig.SparkSpeed.
        /// </summary>
        public double Speed;

        /// <summary>
        /// PlayerState.ExitWasCut just before this spark spawned (kill-verify fix, docs/BIOME_TRAITS.md 7.1): true only for
        /// a re-cut of an exit whose earlier spark KillShield extinguished. The R14 cross-tick cancellation of this spark
        /// restores the flag to this value, so cancelling a re-cut never un-cuts the exit (its loop stays lost, 7.2).
        /// Always false in classic rounds, where the cancellation clears the flag exactly as before.
        /// </summary>
        internal bool ExitWasCutBefore;
    }

    public sealed class PlayerState
    {
        public int Index;
        public byte Id;                               // Id = Index + 1 (grid owner value)
        public string Name;
        public bool IsHuman;
        public Vec2d Pos;
        public Vec2d PrevPos;                         // position at the start of the last tick (render interpolation)
        public int Cell;                              // grid index of the head's current cell (R5); changed only by section 6
        public double Heading;
        public double DesiredHeading;
        public bool Alive = true;
        public bool Home = true;
        public Trail Trail = new Trail();             // empty when home
        public Spark Spark;                           // null when no chase
        public bool Charged;
        public CellMask Pocket;                       // pending pocket cells (Count 0 when none); only an unchased
                                                      // return validates it (contract 24), any other end erases it
        public double EliminatedAt = double.NaN;
        public EliminationCause Cause;
        public int FinalCells;                        // eliminated: owned cells at the start of the eliminating group (R19);
                                                      // alive: at round end
        public int Captures, CutsMade, Kills, PocketsMade;   // Kills: victims eliminated by this player's sparks
                                                             // (credited even if dead). Captures: Returns whose
                                                             // Cells.Length > 0 only (contract 23.2 D2)

        // Core rules made explicit by the kill rewards (docs/BIOME_TRAITS.md 7.1, api additions, kill-core wave D-2).
        // All three keep their neutral value in classic rounds (bit-identical simulation and StateHash).

        /// <summary>
        /// Permanent speed multiplier, 1.0 at spawn, changed only by traits (KillSpeedBoost). The tick speed of section 6
        /// step 1 is PawnSpeed x SpeedMultiplier x (the behaviours' SpeedFactor, i.e. Conduction when home), read at tick
        /// start: a change during a tick applies from the next tick.
        /// </summary>
        public double SpeedMultiplier = 1.0;

        /// <summary>
        /// v1.4 restated as a flag: set when a spark spawns on the current exit, cleared at the next Exit, at the return
        /// and at elimination (and with the spark by the R14 cross-tick cancellation). A return with ExitWasCut captures
        /// nothing (Return.Chased = true), even when the spark was removed in the meantime (KillShield). Classic: always
        /// equal to "Spark != null".
        /// </summary>
        public bool ExitWasCut;

        /// <summary>
        /// Shield end time while shielded (KillShield), double.NegativeInfinity when not. While shielded, enemy heads cannot
        /// cut the trail (no Cut candidate, no spark); the shield ends exactly at that time through the ShieldEnd candidate
        /// of section 6 (ShieldEnded event), and silently at elimination. Territory loss to 0 cells still eliminates.
        /// </summary>
        public double ShieldEnd = double.NegativeInfinity;

        /// <summary>True while shielded (ShieldEnd set). Alive players only carry a shield.</summary>
        public bool Shielded => ShieldEnd > double.NegativeInfinity;

        public int OwnedCells(OwnerGrid g) => g.CountOf(Id);
    }
}
