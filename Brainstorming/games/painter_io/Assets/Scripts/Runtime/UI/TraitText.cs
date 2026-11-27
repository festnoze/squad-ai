// Owned by traits-ui (wave D-2). docs/BIOME_TRAITS.md section 5: the name and the one-line description of a trait,
// Strings keys trait.<Id>.name / trait.<Id>.desc (FR and EN, Id = the TraitId name). The descriptions take the trait's
// parameters, so a moved or retuned trait still describes itself: a SparkSpeed factor below the classic 1.8 reads
// "plus lente", Conduction 1.3 reads "+30 %", KillShield 3 reads "3 s", a KillInheritance share below 1 names its share.
using System;
using System.Collections.Generic;
using PainterIO.Core;

namespace PainterIO.Runtime
{
    public static class TraitText
    {
        /// <summary>"trait.&lt;Id&gt;.name".</summary>
        public static string NameKey(TraitId id) => "trait." + id + ".name";

        /// <summary>"trait.&lt;Id&gt;.desc" (the main description; SparkSpeed and KillInheritance have one variant each).</summary>
        public static string DescKey(TraitId id) => "trait." + id + ".desc";

        /// <summary>The variant keys used by Describe besides trait.&lt;Id&gt;.desc (tests check them in both tables).</summary>
        public static readonly string[] VariantKeys = { "trait.SparkSpeed.desc_slow", "trait.KillInheritance.desc_share" };

        public static string Name(TraitId id) => Name(id, Strings.Language);

        public static string Name(TraitId id, int language) => Strings.Get(NameKey(id), language);

        /// <summary>The one-line description of a spec in the current language.</summary>
        public static string Describe(TraitSpec spec) => Describe(spec, Strings.Language);

        /// <summary>The one-line description of a spec in the given language (0 FR, 1 EN), with its parameters.</summary>
        public static string Describe(TraitSpec spec, int language)
        {
            if (spec == null) return string.Empty;
            TraitId id = spec.Id;
            if (!TraitDefaults.IsKnown(id)) return Strings.Get(DescKey(id), language);
            double p1 = double.IsNaN(spec.P1) ? TraitDefaults.P1(id) : spec.P1;
            double p2 = double.IsNaN(spec.P2) ? TraitDefaults.P2(id) : spec.P2;
            switch (id)
            {
                case TraitId.SparkSpeed:
                    return Strings.FormatIn(language, p1 >= Tuning.SparkSpeedFactor - 1e-9 ? DescKey(id) : "trait.SparkSpeed.desc_slow",
                                            Strings.Decimal(p1, 1, language));
                case TraitId.Propagation:
                case TraitId.ScorchedEarth:
                case TraitId.RingInterval:
                case TraitId.KillShield:
                    return Strings.FormatIn(language, DescKey(id), Seconds(p1, language));
                case TraitId.Conduction:
                case TraitId.ArcReach:
                    return Strings.FormatIn(language, DescKey(id), Percent(p1 - 1.0, language));
                case TraitId.KillInheritance:
                    return p1 >= 0.9995
                        ? Strings.Get(DescKey(id), language)
                        : Strings.FormatIn(language, "trait.KillInheritance.desc_share", Percent(p1, language));
                case TraitId.KillSpeedBoost:
                    return Strings.FormatIn(language, DescKey(id), Percent(p1, language), Percent(p2, language));
                default:
                    return Strings.Get(DescKey(id), language);
            }
        }

        /// <summary>The enabled specs of a set in ascending id order (empty for null or the classic set).</summary>
        public static List<TraitSpec> Enabled(RuleTraits traits)
        {
            var list = new List<TraitSpec>();
            if (traits == null) return list;
            foreach (TraitSpec s in traits.Specs)
            {
                if (s != null && s.Enabled) list.Add(s);
            }
            return list;
        }

        /// <summary>True for the kill reward traits of BIOME_TRAITS section 7 (drawn with the saffron reward rim).</summary>
        public static bool IsKillReward(TraitId id)
        {
            return id == TraitId.KillInheritance || id == TraitId.KillSpeedBoost || id == TraitId.KillShield;
        }

        /// <summary>Seconds as shown in the descriptions and the chips: whole numbers without decimals ("3"), else one ("2,5").</summary>
        public static string Seconds(double seconds, int language)
        {
            if (double.IsNaN(seconds) || double.IsInfinity(seconds)) seconds = 0.0;
            bool whole = Math.Abs(seconds - Math.Round(seconds)) < 0.05;
            return Strings.Decimal(seconds, whole ? 0 : 1, language);
        }

        /// <summary>A fraction as a percent number: 0.3 gives "30", 0.125 gives "12,5" (French) / "12.5" (English).</summary>
        public static string Percent(double fraction, int language)
        {
            if (double.IsNaN(fraction) || double.IsInfinity(fraction)) fraction = 0.0;
            double p = fraction * 100.0;
            bool whole = Math.Abs(p - Math.Round(p)) < 0.05;
            return Strings.Decimal(p, whole ? 0 : 1, language);
        }
    }
}
