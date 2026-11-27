// Owned by traits-infra (wave D-2). docs/BIOME_TRAITS.md section 5 (Runtime architecture) with the default table of
// sections 3 and 7 (kill rewards). A biome is only a default list of traits: this file is the ONE place that knows which
// trait belongs to which biome (Core never sees a biome id).
//
// Resolution of the trait set of a round (BIOME_TRAITS 5):
//   Resolve(biome)         game rounds and the attract match:
//                          defaults (Table) -> SaveData.TraitMatrix overrides -> command line -> master switch
//                          (SaveData.BiomeRulesOn = false, "Regles classiques", gives the classic set).
//   ResolveScripted(biome) DemoScenario sessions (probe, DevShot): CLASSIC unless the command line says otherwise, and
//                          never the saved options, so the probe hash does not depend on the machine's PlayerPrefs.
// Command line (LaunchArgs): -classic (every trait off, wins over everything), -traits "<RuleTraits key>" (the exact set,
// any biome; the value "default" means this biome's line of the table, without the saved matrix), -trait <Id>=0|1 (adds
// or removes one trait on top of the set so far; repeatable, applied in order).
// The trait matrix (hidden test settings, one row per trait, one checkbox per biome) is stored in SaveData.TraitMatrix as
// canonical text: only the rows that differ from the table, ascending trait id, "Id=letters" with L (Liquide), F (Feu),
// E (Electricite) or "-" for no biome, joined by ';' (for example "SparkSpeed=LFE;KillShield=-"); "" = the table. A trait
// assigned to a biome whose line lists it keeps that line's parameters; elsewhere it takes TraitDefaults' parameters.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using PainterIO.Core;
using UnityEngine;

namespace PainterIO.Runtime
{
    public static class BiomeTraitTable
    {
        /// <summary>The value of -traits that selects the biome's default line (probe and DevShot per-biome runs).</summary>
        public const string DefaultKeyword = "default";

        // ------------------------------------------------------------------------------------------------------------
        // THE table (docs/BIOME_TRAITS.md sections 3 and 7). One line per biome, in BiomeId order. Moving a trait to
        // another biome = moving it to another line. Parameters: section 2 (P1, P2).

        private static readonly TraitSpec[][] Table =
        {
            /* Liquide     */ new[] { T(TraitId.Inertia, 420.0), T(TraitId.Coalescence, 2.0), T(TraitId.KillShield, 3.0) },
            /* Feu         */ new[] { T(TraitId.Propagation, 4.0, 1.0), T(TraitId.SparkSpeed, 2.1), T(TraitId.ScorchedEarth, 15.0), T(TraitId.KillInheritance, 1.0) },
            /* Electricite */ new[] { T(TraitId.Conduction, 1.30), T(TraitId.ArcReach, 1.40), T(TraitId.SparkSpeed, 1.5), T(TraitId.RingInterval, 10.0), T(TraitId.KillSpeedBoost, 0.10, 0.30) },
        };

        private static readonly char[] Letters = { 'L', 'F', 'E' };
        private static readonly RuleTraits[] defaults = BuildDefaults();
        private static readonly object logLock = new object();
        private static string loggedArgsError;

        // ------------------------------------------------------------------------------------------------------------
        // Defaults.

        /// <summary>The default trait set of a biome (its line of the table), every trait enabled.</summary>
        public static RuleTraits Defaults(BiomeId biome)
        {
            return defaults[Index(biome)];
        }

        /// <summary>RuleTraits key of the default set (equals TraitTestKit.LiquidV11Key / FireV11Key / ElectricV11Key).</summary>
        public static string DefaultKey(BiomeId biome)
        {
            return Defaults(biome).ToKey();
        }

        /// <summary>True when the biome's line of the table lists the trait.</summary>
        public static bool IsDefault(TraitId id, BiomeId biome)
        {
            return TableSpec(id, Index(biome)) != null;
        }

        /// <summary>Bit b set = the table assigns the trait to biome b (bit 0 Liquide, 1 Feu, 2 Electricite).</summary>
        public static int DefaultMask(TraitId id)
        {
            int mask = 0;
            for (int b = 0; b < BiomeTheme.Count; b++)
            {
                if (TableSpec(id, b) != null) mask |= 1 << b;
            }
            return mask;
        }

        /// <summary>
        /// The spec a trait has when it is assigned to a biome (a new object): the biome's own line when it lists the
        /// trait, else the TraitDefaults parameters.
        /// </summary>
        public static TraitSpec SpecFor(TraitId id, BiomeId biome)
        {
            TraitSpec own = TableSpec(id, Index(biome));
            return own != null ? own.Clone() : TraitDefaults.Spec(id);
        }

        /// <summary>The letter of a biome in the matrix text: L, F or E.</summary>
        public static char LetterOf(BiomeId biome)
        {
            return Letters[Index(biome)];
        }

        // ------------------------------------------------------------------------------------------------------------
        // The trait matrix (SaveData.TraitMatrix).

        /// <summary>Effective assignment of a trait (the saved matrix over the table), as a biome bit mask.</summary>
        public static int MaskOf(TraitId id)
        {
            return MaskOf(id, ParseMatrix(SaveData.TraitMatrix));
        }

        /// <summary>The trait is assigned to the biome in the saved matrix (the table when the matrix is empty).</summary>
        public static bool IsAssigned(TraitId id, BiomeId biome)
        {
            return (MaskOf(id) & (1 << Index(biome))) != 0;
        }

        /// <summary>
        /// Ticks or unticks one checkbox of the matrix: writes the canonical SaveData.TraitMatrix (raises SaveData.Changed).
        /// The next round and the attract match use it (GameDirector restarts the attract match when its traits change).
        /// </summary>
        public static void SetAssigned(TraitId id, BiomeId biome, bool assigned)
        {
            if (!TraitDefaults.IsKnown(id)) throw new ArgumentOutOfRangeException(nameof(id), (int)id, "unknown trait id");
            Dictionary<TraitId, int> overrides = ParseMatrix(SaveData.TraitMatrix);
            int mask = MaskOf(id, overrides);
            int bit = 1 << Index(biome);
            mask = assigned ? mask | bit : mask & ~bit;
            overrides[id] = mask;
            SaveData.TraitMatrix = FormatMatrix(overrides);
        }

        /// <summary>
        /// Parses matrix text into per-trait masks (only the rows present). Lenient: rows "Id=letters" separated by ';',
        /// ids by name (case-insensitive) or number, letters L / F / E in any order and case, "-" or nothing for no
        /// biome; unknown ids, letters and malformed rows are skipped. Null or "" gives no override.
        /// </summary>
        public static Dictionary<TraitId, int> ParseMatrix(string text)
        {
            var result = new Dictionary<TraitId, int>();
            if (string.IsNullOrEmpty(text)) return result;
            string[] rows = text.Split(';');
            for (int r = 0; r < rows.Length; r++)
            {
                string row = rows[r].Trim();
                int eq = row.IndexOf('=');
                if (eq <= 0) continue;
                if (!TryParseTraitId(row.Substring(0, eq).Trim(), out TraitId id)) continue;
                string letters = row.Substring(eq + 1).Trim();
                int mask = 0;
                bool ok = true;
                foreach (char c in letters)
                {
                    char u = char.ToUpperInvariant(c);
                    int b = Array.IndexOf(Letters, u);
                    if (b >= 0) mask |= 1 << b;
                    else if (u != '-' && !char.IsWhiteSpace(u)) ok = false;
                }
                if (ok) result[id] = mask;
            }
            return result;
        }

        /// <summary>
        /// Canonical matrix text of per-trait masks: only the rows that differ from the table, ascending id, "" when the
        /// matrix equals the table.
        /// </summary>
        public static string FormatMatrix(IDictionary<TraitId, int> masks)
        {
            var sb = new StringBuilder();
            IReadOnlyList<TraitId> all = TraitDefaults.All;
            for (int k = 0; k < all.Count; k++)
            {
                TraitId id = all[k];
                if (masks == null || !masks.TryGetValue(id, out int mask)) continue;
                mask &= (1 << BiomeTheme.Count) - 1;
                if (mask == DefaultMask(id)) continue;
                if (sb.Length > 0) sb.Append(';');
                sb.Append(id).Append('=');
                if (mask == 0) sb.Append('-');
                for (int b = 0; b < BiomeTheme.Count; b++)
                {
                    if ((mask & (1 << b)) != 0) sb.Append(Letters[b]);
                }
            }
            return sb.ToString();
        }

        /// <summary>The canonical form of any matrix text (FormatMatrix of ParseMatrix): "" means the table.</summary>
        public static string CanonicalMatrix(string text)
        {
            return FormatMatrix(ParseMatrix(text));
        }

        /// <summary>
        /// The trait set of a biome under a matrix text (pure: no SaveData, no command line). Every trait whose mask has
        /// the biome's bit, enabled, with SpecFor's parameters.
        /// </summary>
        public static RuleTraits FromMatrix(BiomeId biome, string matrixText)
        {
            Dictionary<TraitId, int> overrides = ParseMatrix(matrixText);
            if (overrides.Count == 0) return Defaults(biome);
            int bit = 1 << Index(biome);
            var specs = new List<TraitSpec>();
            IReadOnlyList<TraitId> all = TraitDefaults.All;
            for (int k = 0; k < all.Count; k++)
            {
                if ((MaskOf(all[k], overrides) & bit) != 0) specs.Add(SpecFor(all[k], biome));
            }
            return new RuleTraits(specs);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Resolution.

        /// <summary>
        /// The trait set of a game round or attract match in this biome (BIOME_TRAITS 5): the table, then the saved
        /// matrix, then the command line (-classic, -traits, -trait), then the master switch SaveData.BiomeRulesOn.
        /// </summary>
        public static RuleTraits Resolve(BiomeId biome)
        {
            RuleTraits set = FromMatrix(biome, SaveData.TraitMatrix);
            set = ApplyCommandLine(set, biome);
            if (!SaveData.BiomeRulesOn) return RuleTraits.Classic;
            return set;
        }

        /// <summary>
        /// The trait set of a scripted session (DemoScenario in the probe and DevShot): classic, then the command line
        /// (-traits default = the biome's line of the table). Never reads the saved options.
        /// </summary>
        public static RuleTraits ResolveScripted(BiomeId biome)
        {
            return ApplyCommandLine(RuleTraits.Classic, biome);
        }

        /// <summary>The command-line overrides of LaunchArgs applied to a set (a bad argument is logged once as an error).</summary>
        public static RuleTraits ApplyCommandLine(RuleTraits set, BiomeId biome)
        {
            LogArgsErrorOnce();
            return Compose(set, biome, LaunchArgs.Classic, LaunchArgs.TraitsKey, LaunchArgs.TraitToggles);
        }

        /// <summary>
        /// Pure composition of the command-line overrides (tests): classic wins over everything; traitsKey replaces the set
        /// (DefaultKeyword = the biome's table line; an unparsable key is ignored); each toggle then adds the trait with
        /// SpecFor's parameters (unless already enabled) or removes it.
        /// </summary>
        public static RuleTraits Compose(RuleTraits set, BiomeId biome, bool classic, string traitsKey,
                                         IReadOnlyList<KeyValuePair<TraitId, bool>> toggles)
        {
            if (classic) return RuleTraits.Classic;
            RuleTraits result = set ?? RuleTraits.Classic;
            if (traitsKey != null)
            {
                if (IsDefaultKeyword(traitsKey)) result = Defaults(biome);
                else
                {
                    try
                    {
                        result = RuleTraits.Parse(traitsKey);
                    }
                    catch (FormatException)
                    {
                        // LaunchArgs.TraitArgsError reports it; the set so far stays.
                    }
                }
            }
            if (toggles == null || toggles.Count == 0) return result;
            var specs = new List<TraitSpec>();
            foreach (TraitSpec s in result.Specs)
            {
                if (s.Enabled) specs.Add(s.Clone());
            }
            for (int k = 0; k < toggles.Count; k++)
            {
                TraitId id = toggles[k].Key;
                int at = specs.FindIndex(s => s.Id == id);
                if (toggles[k].Value)
                {
                    if (at < 0) specs.Add(SpecFor(id, biome));
                }
                else if (at >= 0) specs.RemoveAt(at);
            }
            return new RuleTraits(specs);
        }

        /// <summary>True for the -traits values that select the biome's default line ("default", "defaults", "biome").</summary>
        public static bool IsDefaultKeyword(string value)
        {
            if (value == null) return false;
            string v = value.Trim();
            return string.Equals(v, DefaultKeyword, StringComparison.OrdinalIgnoreCase)
                   || string.Equals(v, "defaults", StringComparison.OrdinalIgnoreCase)
                   || string.Equals(v, "biome", StringComparison.OrdinalIgnoreCase);
        }

        /// <summary>A trait id by name (case-insensitive) or number; false for anything else.</summary>
        public static bool TryParseTraitId(string text, out TraitId id)
        {
            id = 0;
            if (string.IsNullOrEmpty(text)) return false;
            string t = text.Trim();
            if (int.TryParse(t, NumberStyles.Integer, CultureInfo.InvariantCulture, out int number))
            {
                id = (TraitId)number;
                return TraitDefaults.IsKnown(id);
            }
            IReadOnlyList<TraitId> all = TraitDefaults.All;
            for (int k = 0; k < all.Count; k++)
            {
                if (string.Equals(all[k].ToString(), t, StringComparison.OrdinalIgnoreCase))
                {
                    id = all[k];
                    return true;
                }
            }
            return false;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Internals.

        private static TraitSpec T(TraitId id, double p1, double p2 = double.NaN)
        {
            return new TraitSpec(id, p1, p2);
        }

        private static int Index(BiomeId biome)
        {
            return (int)BiomeTheme.Clamp((int)biome);
        }

        private static TraitSpec TableSpec(TraitId id, int biomeIndex)
        {
            TraitSpec[] line = Table[biomeIndex];
            for (int k = 0; k < line.Length; k++)
            {
                if (line[k].Id == id) return line[k];
            }
            return null;
        }

        private static int MaskOf(TraitId id, Dictionary<TraitId, int> overrides)
        {
            return overrides != null && overrides.TryGetValue(id, out int mask) ? mask & ((1 << BiomeTheme.Count) - 1) : DefaultMask(id);
        }

        private static RuleTraits[] BuildDefaults()
        {
            var sets = new RuleTraits[Table.Length];
            for (int b = 0; b < Table.Length; b++) sets[b] = new RuleTraits(Table[b]);
            return sets;
        }

        private static void LogArgsErrorOnce()
        {
            string error = LaunchArgs.TraitArgsError;
            if (error == null) return;
            lock (logLock)
            {
                if (error == loggedArgsError) return;
                loggedArgsError = error;
            }
            Debug.LogError("[PainterIO] trait command line: " + error);
        }
    }
}
