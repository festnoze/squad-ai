// Owned by traits-core (wave D-1). docs/BIOME_TRAITS.md section 4.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace PainterIO.Core
{
    /// <summary>
    /// The trait set used by one simulation (docs/BIOME_TRAITS.md section 4). Immutable once built: the constructor
    /// clones the given specs, resolves NaN parameters to the TraitDefaults values, keeps ONE spec per id (the last one
    /// given wins, so a later "Inertia off" overrides an earlier "Inertia on") and stores them in ascending id order.
    /// Disabled specs are kept but inert: Has / Get / ToKey / the simulation ignore them. Classic = the empty set, the
    /// pure brief rules + v1.4 (bit-identical to the simulation without traits).
    /// </summary>
    public sealed class RuleTraits
    {
        private static readonly RuleTraits classic = new RuleTraits(Array.Empty<TraitSpec>());

        private readonly TraitSpec[] specs;
        private readonly IReadOnlyList<TraitSpec> specsView;

        /// <summary>The empty set ("Règles classiques").</summary>
        public static RuleTraits Classic => classic;

        /// <summary>One spec per id present (enabled or not), ascending id. Do not mutate the returned specs.</summary>
        public IReadOnlyList<TraitSpec> Specs => specsView;

        /// <summary>
        /// Builds the set. Throws ArgumentException for a null spec, an unknown id or invalid parameters of an ENABLED
        /// spec (TraitDefaults.Validate). A null sequence gives the classic set.
        /// </summary>
        public RuleTraits(IEnumerable<TraitSpec> specs)
        {
            var byId = new List<TraitSpec>();
            if (specs != null)
            {
                foreach (TraitSpec given in specs)
                {
                    if (given == null) throw new ArgumentException("RuleTraits: null spec", nameof(specs));
                    if (!TraitDefaults.IsKnown(given.Id))
                        throw new ArgumentException("RuleTraits: unknown trait id " + (int)given.Id, nameof(specs));
                    TraitSpec s = given.Clone();
                    if (double.IsNaN(s.P1)) s.P1 = TraitDefaults.P1(s.Id);
                    if (double.IsNaN(s.P2)) s.P2 = TraitDefaults.P2(s.Id);
                    if (s.Enabled)
                    {
                        string error = TraitDefaults.Validate(s);
                        if (error != null) throw new ArgumentException("RuleTraits: " + error, nameof(specs));
                    }
                    int at = IndexOf(byId, s.Id);
                    if (at >= 0) byId[at] = s;   // duplicates: the last spec of an id wins
                    else byId.Add(s);
                }
            }
            byId.Sort((a, b) => ((int)a.Id).CompareTo((int)b.Id));
            this.specs = byId.ToArray();
            specsView = Array.AsReadOnly(this.specs);
        }

        /// <summary>Present AND enabled.</summary>
        public bool Has(TraitId id)
        {
            return Get(id) != null;
        }

        /// <summary>The enabled spec of that id, or null when absent or disabled.</summary>
        public TraitSpec Get(TraitId id)
        {
            for (int k = 0; k < specs.Length; k++)
            {
                if (specs[k].Id == id) return specs[k].Enabled ? specs[k] : null;
            }
            return null;
        }

        /// <summary>True when no trait is enabled (api addition): the round runs the classic rules, bit-identical.</summary>
        public bool IsClassic
        {
            get
            {
                for (int k = 0; k < specs.Length; k++)
                {
                    if (specs[k].Enabled) return false;
                }
                return true;
            }
        }

        /// <summary>Number of enabled traits (api addition).</summary>
        public int EnabledCount
        {
            get
            {
                int n = 0;
                for (int k = 0; k < specs.Length; k++)
                {
                    if (specs[k].Enabled) n++;
                }
                return n;
            }
        }

        /// <summary>
        /// Canonical text of the ENABLED traits, ascending id: "Id(p1,p2);Id(p1,p2)" with invariant round-trip numbers
        /// (for example "Inertia(420,0);Coalescence(2,0)"). The classic set gives "". Used for logs and the hash salt.
        /// </summary>
        public string ToKey()
        {
            var sb = new StringBuilder();
            for (int k = 0; k < specs.Length; k++)
            {
                TraitSpec s = specs[k];
                if (!s.Enabled) continue;
                if (sb.Length > 0) sb.Append(';');
                sb.Append(s.Id).Append('(').Append(TraitSpec.Format(s.P1)).Append(',').Append(TraitSpec.Format(s.P2)).Append(')');
            }
            return sb.ToString();
        }

        /// <summary>
        /// Inverse of ToKey. Also accepts null, "" and "classic" (case-insensitive) for the classic set, ids by name
        /// (case-insensitive) or by number, a bare id ("Propagation": default parameters), one parameter ("SparkSpeed(1.5)")
        /// and whitespace around tokens. Throws FormatException on anything else (unknown id, bad number, invalid
        /// parameter).
        /// </summary>
        public static RuleTraits Parse(string key)
        {
            if (key == null) return Classic;
            string text = key.Trim();
            if (text.Length == 0 || string.Equals(text, "classic", StringComparison.OrdinalIgnoreCase)) return Classic;
            var list = new List<TraitSpec>();
            string[] tokens = text.Split(';');
            for (int t = 0; t < tokens.Length; t++)
            {
                string token = tokens[t].Trim();
                if (token.Length == 0) continue;
                list.Add(ParseToken(token, key));
            }
            try
            {
                return new RuleTraits(list);
            }
            catch (ArgumentException e)
            {
                throw new FormatException("RuleTraits.Parse(\"" + key + "\"): " + e.Message, e);
            }
        }

        /// <summary>Deep copy (api addition): SimConfig.Clone uses it so a running simulation never shares specs.</summary>
        public RuleTraits Clone()
        {
            return specs.Length == 0 ? this : new RuleTraits(specs);
        }

        /// <summary>A new set with this spec added or replacing the spec of its id (api addition, for overrides).</summary>
        public RuleTraits With(TraitSpec spec)
        {
            if (spec == null) throw new ArgumentNullException(nameof(spec));
            var list = new List<TraitSpec>(specs) { spec };
            return new RuleTraits(list);
        }

        /// <summary>"classic" for the classic set, else ToKey().</summary>
        public override string ToString()
        {
            return IsClassic ? "classic" : ToKey();
        }

        /// <summary>Value equality: the same specs (id, Enabled, P1, P2) in the same order, disabled ones included.</summary>
        public override bool Equals(object obj)
        {
            if (ReferenceEquals(this, obj)) return true;
            if (!(obj is RuleTraits other) || other.specs.Length != specs.Length) return false;
            for (int k = 0; k < specs.Length; k++)
            {
                TraitSpec a = specs[k], b = other.specs[k];
                if (a.Id != b.Id || a.Enabled != b.Enabled || !a.P1.Equals(b.P1) || !a.P2.Equals(b.P2)) return false;
            }
            return true;
        }

        public override int GetHashCode()
        {
            unchecked
            {
                int h = 17;
                for (int k = 0; k < specs.Length; k++)
                {
                    h = h * 31 + (int)specs[k].Id;
                    h = h * 31 + (specs[k].Enabled ? 1 : 0);
                    h = h * 31 + specs[k].P1.GetHashCode();
                    h = h * 31 + specs[k].P2.GetHashCode();
                }
                return h;
            }
        }

        private static TraitSpec ParseToken(string token, string key)
        {
            string name = token;
            string args = null;
            int open = token.IndexOf('(');
            if (open >= 0)
            {
                if (!token.EndsWith(")", StringComparison.Ordinal)) throw Bad(key, "missing ')' in \"" + token + "\"");
                name = token.Substring(0, open).Trim();
                args = token.Substring(open + 1, token.Length - open - 2);
            }
            if (!TryParseId(name, out TraitId id)) throw Bad(key, "unknown trait \"" + name + "\"");
            var spec = new TraitSpec(id);
            if (args != null && args.Trim().Length > 0)
            {
                string[] parts = args.Split(',');
                if (parts.Length > 2) throw Bad(key, "too many parameters in \"" + token + "\"");
                spec.P1 = ParseNumber(parts[0], key);
                if (parts.Length == 2) spec.P2 = ParseNumber(parts[1], key);
            }
            return spec;
        }

        private static bool TryParseId(string name, out TraitId id)
        {
            id = 0;
            if (int.TryParse(name, NumberStyles.Integer, CultureInfo.InvariantCulture, out int number))
            {
                id = (TraitId)number;
                return TraitDefaults.IsKnown(id);
            }
            IReadOnlyList<TraitId> all = TraitDefaults.All;
            for (int k = 0; k < all.Count; k++)
            {
                if (string.Equals(all[k].ToString(), name, StringComparison.OrdinalIgnoreCase))
                {
                    id = all[k];
                    return true;
                }
            }
            return false;
        }

        private static double ParseNumber(string text, string key)
        {
            if (!double.TryParse(text.Trim(), NumberStyles.Float, CultureInfo.InvariantCulture, out double v))
                throw Bad(key, "bad number \"" + text + "\"");
            return v;
        }

        private static FormatException Bad(string key, string why)
        {
            return new FormatException("RuleTraits.Parse(\"" + key + "\"): " + why);
        }

        private static int IndexOf(List<TraitSpec> list, TraitId id)
        {
            for (int k = 0; k < list.Count; k++)
            {
                if (list[k].Id == id) return k;
            }
            return -1;
        }
    }
}
