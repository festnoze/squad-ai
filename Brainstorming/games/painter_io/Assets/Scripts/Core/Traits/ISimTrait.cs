// Owned by traits-core (wave D-1). docs/BIOME_TRAITS.md section 4 (binding signatures).
using System.Collections.Generic;

namespace PainterIO.Core
{
    /// <summary>
    /// One behaviour trait (Core/Traits/&lt;Id&gt;Trait.cs). The Simulation creates one instance per enabled behaviour
    /// trait (TraitRegistry.CreateBehaviours, TraitId order), attaches it once in its constructor, then calls the hooks
    /// at the points of the section 6 event engine. Hooks must be deterministic (no wall clock, no Dictionary order, Rng
    /// only), must not test the biome, and may mutate only what their hook allows.
    /// </summary>
    public interface ISimTrait
    {
        TraitId Id { get; }

        /// <summary>Called once by the Simulation constructor, after the grid and players exist (spec = its enabled spec).</summary>
        void Attach(Simulation sim, TraitSpec spec);

        /// <summary>
        /// Section 6 step 1, per alive player, after the controllers were polled and before motion: the factor applied to
        /// PawnSpeed for this tick (the spark speed is not affected). 1.0 when not concerned. Factors of several traits
        /// multiply.
        /// </summary>
        double SpeedFactor(Simulation sim, PlayerState p);

        /// <summary>
        /// Section 6 step a, UNCHASED returns only, before the R18 conflict rule: cells holds the returner's captured cells
        /// (ascending, computed against the grid as it is just before the instant, which is not mutated yet); a trait may
        /// add cells (the Simulation sorts and de-duplicates afterwards). Added cells become part of the Return's Cells.
        /// Simulation.TraitTime is the group time of the return.
        /// </summary>
        void AugmentCapture(Simulation sim, PlayerState p, List<int> cells);

        /// <summary>After a player's cells were neutralized (freedCells ascending, read-only), at group time 'time'.</summary>
        void OnEliminated(Simulation sim, PlayerState p, int[] freedCells, double time);

        /// <summary>
        /// Section 6 step 3, after the trail appends, positions and sparks, before the ring spawner; Simulation.Time is the
        /// tick end time and Simulation.TickStartTime the tick start time. Never called once the round has ended. Events
        /// added to 'raised' are emitted by the Simulation in list order after every trait ran.
        /// </summary>
        void EndOfTick(Simulation sim, List<SimEvent> raised);
    }

    /// <summary>
    /// Optional companion of ISimTrait for traits whose SpeedFactor can exceed 1 (api addition): the largest factor the
    /// attached trait can return. The Simulation constructor checks HeadGrace &gt; PawnSpeed x (largest factor) x Dt.
    /// </summary>
    public interface ISpeedTrait
    {
        double MaxSpeedFactor { get; }
    }

    /// <summary>
    /// One kill of an event group (docs/BIOME_TRAITS.md section 7, api addition, kill-core wave D-2): a Spark elimination
    /// whose killer (Spark.Attacker, R11) is still alive after every elimination of the group. Data only, read-only for
    /// the traits.
    /// </summary>
    public sealed class KillInfo
    {
        /// <summary>The killer's player index (Spark.Attacker).</summary>
        public int Killer;

        /// <summary>The victim's player index.</summary>
        public int Victim;

        /// <summary>The group time (= EliminatedAt of the victim, = SparkCaught.Time).</summary>
        public double Time;

        /// <summary>The victim's head at the kill (SparkCaught.Point).</summary>
        public Vec2d Point;

        /// <summary>The cells the elimination freed (Eliminated.Cells, ascending). Still neutral when OnKill runs.</summary>
        public int[] FreedCells;

        /// <summary>
        /// Rule v1.6 (contract 30): the victim's spark at the kill (SCut and the cut geometry). Set only in single-domain
        /// rounds (KillInheritance with SimConfig.InheritanceBridge on), else null.
        /// </summary>
        internal Spark Spark;

        /// <summary>
        /// Rule v1.6: the victim's trail from its exit to the cut point P = PointAt(SCut) (the part that tied it to its
        /// land), copied before the elimination cleared the trail. Set only in single-domain rounds, else null.
        /// </summary>
        internal List<Vec2d> VictimPrefix;
    }

    /// <summary>
    /// Optional companion of ISimTrait for the kill rewards (docs/BIOME_TRAITS.md section 7, api addition). A KILL is a
    /// Spark elimination; the killer is Spark.Attacker. After step b of a section 6 group (the last step that can eliminate
    /// a player, so "alive after step b" = "alive after the group"), the Simulation calls OnKill once per kill whose killer
    /// is alive, in elimination order (ascending victim index), and for each kill every attached kill trait in TraitId order.
    /// Kills whose killer is dead or was eliminated in the same group get no call (their cells stay neutral, R13). A
    /// TerritoryLost elimination is never a kill. Simulation.TraitTime is the group time. Events added to 'raised' are
    /// emitted right after the call, in list order. A kill trait may change the killer's state and the victim's freed
    /// cells; the next candidate computation (section 6, uCur = uG) sees the result, so for example an inherited cell under
    /// the killer's trailing head returns it at that instant through the normal state check.
    /// </summary>
    public interface IKillTrait
    {
        void OnKill(Simulation sim, KillInfo kill, List<SimEvent> raised);
    }
}
