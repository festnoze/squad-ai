// Owned by traits-core (wave D-1). docs/BIOME_TRAITS.md section 2 (the trait catalogue and its default parameters).
using System;
using System.Collections.Generic;

namespace PainterIO.Core
{
    /// <summary>
    /// The trait catalogue as data (docs/BIOME_TRAITS.md section 2): kind, default parameters, parameter names and valid
    /// ranges per trait. Biome assignments are NOT here (Runtime BiomeTraitTable, section 3 / 5): nothing in Core knows
    /// biomes. Adding a trait = one TraitId value, one row in Rows, one line in TraitRegistry and, for a behaviour trait,
    /// one Core/Traits/&lt;Id&gt;Trait.cs file.
    /// </summary>
    public static class TraitDefaults
    {
        /// <summary>Inertia P1: max turn rate in degrees per second (Tuning.TurnRateDeg is 540).</summary>
        public const double InertiaTurnRateDeg = 420.0;

        /// <summary>Coalescence P1: holes strictly smaller than this area (u^2) are filled.</summary>
        public const double CoalescenceMaxHoleArea = 2.0;

        /// <summary>SparkSpeed P1: the SparkSpeedFactor override (section 3 uses 2.1 and 1.5 depending on the biome).</summary>
        public const double SparkSpeedFactor = 2.1;

        /// <summary>Propagation P1: seconds between two growth instants (multiples of Interval).</summary>
        public const double PropagationInterval = 4.0;

        /// <summary>Propagation P2: rings grown at each instant.</summary>
        public const double PropagationRings = 1.0;

        /// <summary>ScorchedEarth P1: seconds the freed cells of an eliminated player stay scorched.</summary>
        public const double ScorchedEarthDuration = 15.0;

        /// <summary>Conduction P1: speed factor of a player whose current cell is its own at tick start.</summary>
        public const double ConductionHomeSpeedFactor = 1.30;

        /// <summary>ArcReach P1: SimConfig.ContactScale (cut contact radius multiplier).</summary>
        public const double ArcReachContactScale = 1.40;

        /// <summary>RingInterval P1: LassoFirstSpawn and LassoRespawn override (seconds).</summary>
        public const double RingIntervalSeconds = 10.0;

        /// <summary>KillInheritance P1: share of the victim's cells that go to a surviving killer (section 7, 1.0 = all).</summary>
        public const double KillInheritanceShare = 1.0;

        /// <summary>KillSpeedBoost P1: added to the killer's SpeedMultiplier per kill (section 7).</summary>
        public const double KillSpeedBoostPerKill = 0.10;

        /// <summary>KillSpeedBoost P2: the multiplier is capped at 1 + Cap (section 7).</summary>
        public const double KillSpeedBoostCap = 0.30;

        /// <summary>KillShield P1: seconds of invincibility after a kill (section 7).</summary>
        public const double KillShieldDuration = 3.0;

        /// <summary>Catalogue row of one trait.</summary>
        private sealed class Row
        {
            public TraitId Id;
            public TraitKind Kind;
            public double P1, P2;                // defaults
            public string P1Name, P2Name;        // null when the parameter is unused
            public double P1Min;                 // valid when P1 >= P1Min (or > P1Min when P1MinExclusive)
            public bool P1MinExclusive;
            public double P1Max = double.PositiveInfinity;   // valid when P1 <= P1Max
            public double P2Min = double.NegativeInfinity;   // valid when P2 >= P2Min
        }

        private static readonly Row[] Rows =
        {
            new Row { Id = TraitId.Inertia, Kind = TraitKind.Config, P1 = InertiaTurnRateDeg, P2 = 0.0, P1Name = "TurnRateDeg", P1Min = 0.0 },
            new Row { Id = TraitId.Coalescence, Kind = TraitKind.Behaviour, P1 = CoalescenceMaxHoleArea, P2 = 0.0, P1Name = "MaxHoleArea", P1Min = 0.0 },
            new Row { Id = TraitId.SparkSpeed, Kind = TraitKind.Config, P1 = SparkSpeedFactor, P2 = 0.0, P1Name = "Factor", P1Min = 1.0, P1MinExclusive = true },
            new Row { Id = TraitId.Propagation, Kind = TraitKind.Behaviour, P1 = PropagationInterval, P2 = PropagationRings, P1Name = "Interval", P2Name = "Rings", P1Min = 0.0, P1MinExclusive = true },
            new Row { Id = TraitId.ScorchedEarth, Kind = TraitKind.Behaviour, P1 = ScorchedEarthDuration, P2 = 0.0, P1Name = "Duration", P1Min = 0.0 },
            new Row { Id = TraitId.Conduction, Kind = TraitKind.Behaviour, P1 = ConductionHomeSpeedFactor, P2 = 0.0, P1Name = "HomeSpeedFactor", P1Min = 0.0, P1MinExclusive = true },
            new Row { Id = TraitId.ArcReach, Kind = TraitKind.Config, P1 = ArcReachContactScale, P2 = 0.0, P1Name = "ContactScale", P1Min = 0.0, P1MinExclusive = true },
            new Row { Id = TraitId.RingInterval, Kind = TraitKind.Config, P1 = RingIntervalSeconds, P2 = 0.0, P1Name = "Seconds", P1Min = 0.0 },
            new Row { Id = TraitId.KillInheritance, Kind = TraitKind.Behaviour, P1 = KillInheritanceShare, P2 = 0.0, P1Name = "Share", P1Min = 0.0, P1Max = 1.0 },
            new Row { Id = TraitId.KillSpeedBoost, Kind = TraitKind.Behaviour, P1 = KillSpeedBoostPerKill, P2 = KillSpeedBoostCap, P1Name = "PerKill", P2Name = "Cap", P1Min = 0.0, P2Min = 0.0 },
            new Row { Id = TraitId.KillShield, Kind = TraitKind.Behaviour, P1 = KillShieldDuration, P2 = 0.0, P1Name = "Duration", P1Min = 0.0 },
        };

        private static readonly TraitId[] all = BuildAll();

        /// <summary>Every trait id in ascending order.</summary>
        public static IReadOnlyList<TraitId> All => all;

        /// <summary>True for a defined TraitId value.</summary>
        public static bool IsKnown(TraitId id)
        {
            return Find(id) != null;
        }

        public static TraitKind KindOf(TraitId id) => Get(id).Kind;

        public static double P1(TraitId id) => Get(id).P1;

        public static double P2(TraitId id) => Get(id).P2;

        /// <summary>Name of P1 / P2 (null when unused), for logs and the hidden test settings.</summary>
        public static string ParameterName(TraitId id, int index) => index == 1 ? Get(id).P1Name : Get(id).P2Name;

        /// <summary>A new enabled spec with the default parameters.</summary>
        public static TraitSpec Spec(TraitId id) => new TraitSpec(id);

        /// <summary>A new enabled spec with p1 (and p2; NaN keeps a default).</summary>
        public static TraitSpec Spec(TraitId id, double p1, double p2 = double.NaN) => new TraitSpec(id, p1, p2);

        /// <summary>
        /// Null when the spec's parameters are usable, else the reason. Parameters must be finite; P1 respects the row's
        /// minimum (SparkSpeed &gt; 1 so the spark stays faster than the pawn, Propagation Interval &gt; 0, Conduction and
        /// ArcReach &gt; 0, the others &gt;= 0); Propagation Rings must be a whole number &gt;= 0 (rounded). Kill traits
        /// (section 7): KillInheritance Share in [0, 1], KillSpeedBoost PerKill and Cap &gt;= 0, KillShield Duration &gt;= 0.
        /// </summary>
        public static string Validate(TraitSpec spec)
        {
            if (spec == null) return "null spec";
            Row row = Find(spec.Id);
            if (row == null) return "unknown trait id " + (int)spec.Id;
            if (double.IsNaN(spec.P1) || double.IsInfinity(spec.P1)) return spec.Id + ": P1 (" + row.P1Name + ") must be finite";
            if (double.IsNaN(spec.P2) || double.IsInfinity(spec.P2)) return spec.Id + ": P2 must be finite";
            bool ok = row.P1MinExclusive ? spec.P1 > row.P1Min : spec.P1 >= row.P1Min;
            if (!ok) return spec.Id + ": P1 (" + row.P1Name + ") must be " + (row.P1MinExclusive ? "> " : ">= ") + TraitSpec.Format(row.P1Min);
            if (spec.P1 > row.P1Max) return spec.Id + ": P1 (" + row.P1Name + ") must be <= " + TraitSpec.Format(row.P1Max);
            if (spec.P2 < row.P2Min) return spec.Id + ": P2 (" + row.P2Name + ") must be >= " + TraitSpec.Format(row.P2Min);
            if (spec.Id == TraitId.Propagation && !(spec.P2 >= 0.0 && spec.P2 <= 64.0))
                return spec.Id + ": P2 (Rings) must be in [0, 64]";
            return null;
        }

        private static Row Get(TraitId id)
        {
            Row row = Find(id);
            if (row == null) throw new ArgumentOutOfRangeException(nameof(id), (int)id, "unknown trait id");
            return row;
        }

        private static Row Find(TraitId id)
        {
            for (int k = 0; k < Rows.Length; k++)
            {
                if (Rows[k].Id == id) return Rows[k];
            }
            return null;
        }

        private static TraitId[] BuildAll()
        {
            var ids = new TraitId[Rows.Length];
            for (int k = 0; k < Rows.Length; k++) ids[k] = Rows[k].Id;
            Array.Sort(ids);
            return ids;
        }
    }
}
