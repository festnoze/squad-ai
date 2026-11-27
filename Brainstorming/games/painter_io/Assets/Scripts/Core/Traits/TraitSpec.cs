// Owned by traits-core (wave D-1). docs/BIOME_TRAITS.md section 4.
using System.Globalization;

namespace PainterIO.Core
{
    /// <summary>
    /// Data only: one trait with its parameters (docs/BIOME_TRAITS.md section 2 gives the meaning of P1 and P2 per trait).
    /// A parameter left at NaN (the field default) means "the TraitDefaults value"; RuleTraits resolves it when the spec
    /// enters a set, so every spec held by a RuleTraits has concrete values. Specs read from a RuleTraits must not be
    /// mutated (use Clone()).
    /// </summary>
    public sealed class TraitSpec
    {
        public TraitId Id;
        public bool Enabled = true;

        /// <summary>First parameter (section 2). NaN = TraitDefaults.P1(Id).</summary>
        public double P1 = double.NaN;

        /// <summary>Second parameter (section 2, only Propagation uses it: Rings). NaN = TraitDefaults.P2(Id).</summary>
        public double P2 = double.NaN;

        public TraitSpec()
        {
        }

        /// <summary>The trait with its default parameters, enabled.</summary>
        public TraitSpec(TraitId id)
        {
            Id = id;
            P1 = TraitDefaults.P1(id);
            P2 = TraitDefaults.P2(id);
        }

        /// <summary>The trait with explicit parameters (NaN keeps the default), enabled unless told otherwise.</summary>
        public TraitSpec(TraitId id, double p1, double p2 = double.NaN, bool enabled = true)
        {
            Id = id;
            P1 = double.IsNaN(p1) ? TraitDefaults.P1(id) : p1;
            P2 = double.IsNaN(p2) ? TraitDefaults.P2(id) : p2;
            Enabled = enabled;
        }

        /// <summary>Field-by-field copy.</summary>
        public TraitSpec Clone()
        {
            return (TraitSpec)MemberwiseClone();
        }

        /// <summary>"Id(p1,p2)" with invariant round-trip numbers (the RuleTraits key token), plus " off" when disabled.</summary>
        public override string ToString()
        {
            return Id + "(" + Format(P1) + "," + Format(P2) + ")" + (Enabled ? "" : " off");
        }

        internal static string Format(double v)
        {
            return v.ToString("R", CultureInfo.InvariantCulture);
        }
    }
}
