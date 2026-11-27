// Owned by BI since wave B-2 (written by B4). Contract 15.6: every visible text goes through Strings.Get (French default, English table), and every number
// shown to the player goes through the formatters below (decimal comma in French, point in English, culture independent).
// Player names: "name.you" (Toi / You) and "name.color0".."name.color3" (Corail, Lagon, Safran, Lilas), see Palette.
using System;
using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

namespace PainterIO.Runtime
{
    public static class Strings
    {
        public const int French = 0;
        public const int English = 1;

        /// <summary>The keys contract 15.6 names explicitly (EditMode tests assert they exist in both tables).</summary>
        public static readonly string[] RequiredKeys =
        {
            "pause.title", "pause.resume", "pause.restart", "pause.menu", "quit.title", "quit.yes", "quit.no", "hint.steer",
            "toast.spark_kill", "results.saved_close", "results.last_survivor", "results.all_eliminated", "results.stats",
            "results.tuning_modified", "options.test_settings", "name.you", "name.color0", "name.color1", "name.color2",
            "name.color3",
        };

        private static readonly Dictionary<string, string> Fr = new Dictionary<string, string>
        {
            // Number formats (used by the formatters, not shown alone).
            { "fmt.decimal", "," },
            { "fmt.percent", "{0} %" },
            { "fmt.gain", "+{0}" },

            // Player names.
            { "name.you", "Toi" },
            { "name.color0", "Corail" },
            { "name.color1", "Lagon" },
            { "name.color2", "Safran" },
            { "name.color3", "Lilas" },

            // Menu (15.2).
            { "menu.title", "Painter.io" },
            { "menu.play", "JOUER" },
            { "menu.options", "Options" },
            { "menu.color", "Ta couleur" },
            { "menu.best", "Meilleur : {0} · {1}" },
            { "menu.wins.one", "{0} victoire" },
            { "menu.wins.other", "{0} victoires" },
            { "menu.biome", "Biome" },

            // Biomes (25.1).
            { "biome.liquid", "Liquide" },
            { "biome.fire", "Feu" },
            { "biome.electric", "Électricité" },

            // Options (15.2).
            { "options.title", "Options" },
            { "options.sound", "Son" },
            { "options.haptics", "Vibrations" },
            { "options.lasso", "Bonus lasso" },
            { "options.language", "Langue" },
            { "options.lang_fr", "FR" },
            { "options.lang_en", "EN" },
            { "options.quality", "Qualité" },
            { "options.quality_auto", "Auto" },
            { "options.quality_high", "Haute" },
            { "options.quality_medium", "Moyenne" },
            { "options.quality_low", "Basse" },
            { "options.version", "Version {0}" },
            { "options.test_settings", "Réglages de test" },
            { "options.spark", "Vitesse étincelle" },
            { "options.round", "Durée de manche" },
            { "options.ring", "Délai anneau" },
            { "options.factor_value", "× {0}" },
            { "options.seconds_value", "{0} s" },
            { "options.reset", "Réinitialiser" },
            { "options.close", "Fermer" },

            // HUD (15.3).
            { "hud.out", "éliminé" },
            { "toast.eliminated", "{0} a été éliminé" },
            { "toast.cut", "Tu as coupé {0} !" },
            { "toast.spark_kill", "Ton étincelle a eu {0} !" },
            { "toast.lasso_ready", "Lasso prêt !" },

            // Tutorial (15.4; brief section 1 verbatim, the first-cut line as changed by the user in contract 24, v1.4).
            { "hint.steer", "Glisse ton doigt pour diriger" },
            { "tut.exit", "Sors de ta couleur et reviens pour agrandir ton terrain." },
            { "tut.cut", "On a coupé ton trait ! Rentre avant l’étincelle pour rester en vie." },
            { "tut.lasso", "Lasso ! Recroise ton fil pour enfermer une poche, puis rentre." },
            // Wave C (rules-01): shown once, at the first unchased return after an uncharged crossing of the own trail.
            { "tut.selfcross", "Recroiser ton fil ouvre ta boucle : rentre sans le recroiser pour tout peindre." },

            // Results (15.5; the saved lines as changed by contract 24, v1.4: a saved chased return captures nothing).
            { "results.rank.1", "1er" },
            { "results.rank.2", "2e" },
            { "results.rank.3", "3e" },
            { "results.rank.4", "4e" },
            { "results.rank.n", "{0}e" },
            { "results.tied", "Ex æquo {0}" },
            { "results.area_caption", "surface finale" },
            { "results.saved", "Rentré {0} s avant l’étincelle : boucle perdue." },
            { "results.saved_close", "Sauvé de justesse : boucle perdue." },
            { "results.caught", "{0} t’a coupé : rattrapé à {1} m de chez toi." },
            { "results.caught_nodist", "{0} t’a coupé : l’étincelle t’a rattrapé." },
            { "results.caught_unknown", "L’étincelle t’a rattrapé à {0} m de chez toi." },
            { "results.territory_lost", "Ton dernier morceau de terrain a été pris." },
            { "results.time_up", "Temps écoulé." },
            { "results.last_survivor", "Dernier survivant !" },
            { "results.all_eliminated", "Éliminés au même instant" },
            { "results.stats", "{0} · {1} · {2} · {3} · {4}" },
            { "results.stat.captures.one", "{0} capture" },
            { "results.stat.captures.other", "{0} captures" },
            { "results.stat.cuts.one", "{0} coupe" },
            { "results.stat.cuts.other", "{0} coupes" },
            { "results.stat.kills.one", "{0} élimination" },
            { "results.stat.kills.other", "{0} éliminations" },
            { "results.stat.pockets.one", "{0} poche" },
            { "results.stat.pockets.other", "{0} poches" },
            { "results.tuning_modified", "réglages modifiés" },
            { "results.replay", "REJOUER" },
            { "results.menu", "MENU" },

            // Pause and quit (15.7).
            { "pause.title", "Pause" },
            { "pause.resume", "REPRENDRE" },
            { "pause.restart", "RECOMMENCER" },
            { "pause.menu", "MENU" },
            { "quit.title", "Quitter ?" },
            { "quit.yes", "OUI" },
            { "quit.no", "NON" },
        };

        private static readonly Dictionary<string, string> En = new Dictionary<string, string>
        {
            { "fmt.decimal", "." },
            { "fmt.percent", "{0}%" },
            { "fmt.gain", "+{0}" },

            { "name.you", "You" },
            { "name.color0", "Coral" },
            { "name.color1", "Teal" },
            { "name.color2", "Saffron" },
            { "name.color3", "Lilac" },

            { "menu.title", "Painter.io" },
            { "menu.play", "PLAY" },
            { "menu.options", "Options" },
            { "menu.color", "Your color" },
            { "menu.best", "Best: {0} · {1}" },
            { "menu.wins.one", "{0} win" },
            { "menu.wins.other", "{0} wins" },
            { "menu.biome", "Biome" },

            { "biome.liquid", "Liquid" },
            { "biome.fire", "Fire" },
            { "biome.electric", "Electricity" },

            { "options.title", "Options" },
            { "options.sound", "Sound" },
            { "options.haptics", "Vibration" },
            { "options.lasso", "Lasso bonus" },
            { "options.language", "Language" },
            { "options.lang_fr", "FR" },
            { "options.lang_en", "EN" },
            { "options.quality", "Quality" },
            { "options.quality_auto", "Auto" },
            { "options.quality_high", "High" },
            { "options.quality_medium", "Medium" },
            { "options.quality_low", "Low" },
            { "options.version", "Version {0}" },
            { "options.test_settings", "Test settings" },
            { "options.spark", "Spark speed" },
            { "options.round", "Round length" },
            { "options.ring", "Ring delay" },
            { "options.factor_value", "× {0}" },
            { "options.seconds_value", "{0} s" },
            { "options.reset", "Reset" },
            { "options.close", "Close" },

            { "hud.out", "out" },
            { "toast.eliminated", "{0} was eliminated" },
            { "toast.cut", "You cut {0}!" },
            { "toast.spark_kill", "Your spark got {0}!" },
            { "toast.lasso_ready", "Lasso ready!" },

            { "hint.steer", "Swipe to steer" },
            { "tut.exit", "Leave your color and come back to grow your land." },
            { "tut.cut", "Your thread was cut! Get home before the spark to stay alive." },
            { "tut.lasso", "Lasso! Cross your thread again to close a pocket, then go home." },
            { "tut.selfcross", "Crossing your own thread breaks the loop: come home without crossing it to paint it all." },

            { "results.rank.1", "1st" },
            { "results.rank.2", "2nd" },
            { "results.rank.3", "3rd" },
            { "results.rank.4", "4th" },
            { "results.rank.n", "{0}th" },
            { "results.tied", "Tied {0}" },
            { "results.area_caption", "final area" },
            { "results.saved", "Home {0} s ahead of the spark: loop lost." },
            { "results.saved_close", "Saved by a hair: loop lost." },
            { "results.caught", "{0} cut you: caught {1} m from home." },
            { "results.caught_nodist", "{0} cut you: the spark caught you." },
            { "results.caught_unknown", "The spark caught you {0} m from home." },
            { "results.territory_lost", "Your last piece of land was taken." },
            { "results.time_up", "Time's up." },
            { "results.last_survivor", "Last survivor!" },
            { "results.all_eliminated", "Eliminated at the same instant" },
            { "results.stats", "{0} · {1} · {2} · {3} · {4}" },
            { "results.stat.captures.one", "{0} capture" },
            { "results.stat.captures.other", "{0} captures" },
            { "results.stat.cuts.one", "{0} cut" },
            { "results.stat.cuts.other", "{0} cuts" },
            { "results.stat.kills.one", "{0} elimination" },
            { "results.stat.kills.other", "{0} eliminations" },
            { "results.stat.pockets.one", "{0} pocket" },
            { "results.stat.pockets.other", "{0} pockets" },
            { "results.tuning_modified", "modified settings" },
            { "results.replay", "PLAY AGAIN" },
            { "results.menu", "MENU" },

            { "pause.title", "Paused" },
            { "pause.resume", "RESUME" },
            { "pause.restart", "RESTART" },
            { "pause.menu", "MENU" },
            { "quit.title", "Quit?" },
            { "quit.yes", "YES" },
            { "quit.no", "NO" },
        };

        private static readonly HashSet<string> missingLogged = new HashSet<string>();

        private static int languageOverride = -2;   // -2 not read yet, -1 none, else the "-lang fr|en" command-line value

        /// <summary>
        /// 0 FR (default), 1 EN; backed by SaveData.Language. The command line "-lang fr|en" overrides it for the session
        /// without saving (screenshots, playtests); setting the language (Options) clears that override.
        /// </summary>
        public static int Language
        {
            get
            {
                if (languageOverride == -2) languageOverride = ReadLanguageOverride();
                if (languageOverride >= 0) return languageOverride;
                return SaveData.Language == English ? English : French;
            }
            set
            {
                languageOverride = -1;
                SaveData.Language = value == English ? English : French;
            }
        }

        private static int ReadLanguageOverride()
        {
            try
            {
                string v = LaunchArgs.Value("-lang");
                if (string.IsNullOrEmpty(v)) return -1;
                v = v.Trim().ToLowerInvariant();
                if (v == "en" || v == "1") return English;
                if (v == "fr" || v == "0") return French;
            }
            catch (Exception)
            {
                // No command line: no override.
            }
            return -1;
        }

        /// <summary>The text of key in the current language (French when the English entry is missing, the key itself last).</summary>
        public static string Get(string key)
        {
            return Get(key, Language);
        }

        /// <summary>The text of key in the given language (0 FR, 1 EN). Never null.</summary>
        public static string Get(string key, int language)
        {
            if (string.IsNullOrEmpty(key)) return string.Empty;
            Dictionary<string, string> table = language == English ? En : Fr;
            if (table.TryGetValue(key, out string value)) return value;
            if (Fr.TryGetValue(key, out value)) return value;
            if (missingLogged.Add(key)) Debug.LogWarning("[PainterIO] Strings: missing key '" + key + "'");
            return key;
        }

        /// <summary>string.Format of the key's text (current language) with already formatted arguments.</summary>
        public static string Format(string key, params object[] args)
        {
            return FormatIn(Language, key, args);
        }

        /// <summary>string.Format of the key's text in the given language.</summary>
        public static string FormatIn(int language, string key, params object[] args)
        {
            string pattern = Get(key, language);
            try
            {
                return string.Format(CultureInfo.InvariantCulture, pattern, args);
            }
            catch (FormatException)
            {
                return pattern;
            }
        }

        /// <summary>True when the table of the language (0 FR, 1 EN) has the key.</summary>
        public static bool Has(string key, int language)
        {
            return key != null && (language == English ? En : Fr).ContainsKey(key);
        }

        /// <summary>Every key of the table of the language (0 FR, 1 EN), for tests.</summary>
        public static IEnumerable<string> Keys(int language)
        {
            return (language == English ? En : Fr).Keys;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Number formatting (culture independent: invariant digits, then the table's decimal separator).

        /// <summary>value rounded to the given decimals ("0,4" in French, "0.4" in English).</summary>
        public static string Decimal(double value, int decimals)
        {
            return Decimal(value, decimals, Language);
        }

        public static string Decimal(double value, int decimals, int language)
        {
            if (double.IsNaN(value) || double.IsInfinity(value)) value = 0.0;
            decimals = Mathf.Clamp(decimals, 0, 6);
            double r = Math.Round(value, decimals, MidpointRounding.AwayFromZero);
            if (r == 0.0) r = 0.0;   // no "-0,0"
            string s = r.ToString(decimals == 0 ? "0" : "0." + new string('0', decimals), CultureInfo.InvariantCulture);
            string sep = Get("fmt.decimal", language);
            return sep == "." ? s : s.Replace(".", sep);
        }

        /// <summary>
        /// An area percent as the HUD shows it (15.3): one decimal below 10 % ("3,4 %", EN "3.4%"), whole numbers from
        /// 10 % on ("28 %", EN "28%").
        /// </summary>
        public static string Area(double percent)
        {
            return Area(percent, Language);
        }

        public static string Area(double percent, int language)
        {
            return FormatIn(language, "fmt.percent", AreaNumber(percent, language));
        }

        /// <summary>A capture gain ("+2,1 %", EN "+2.1%"), same decimals rule as Area.</summary>
        public static string Gain(double percent)
        {
            return Gain(percent, Language);
        }

        public static string Gain(double percent, int language)
        {
            return FormatIn(language, "fmt.gain", Area(percent, language));
        }

        /// <summary>The countdown "01:30": minutes and seconds of the remaining time, seconds rounded up.</summary>
        public static string Clock(double seconds)
        {
            if (double.IsNaN(seconds) || seconds < 0.0) seconds = 0.0;
            long s = (long)Math.Ceiling(seconds - 1e-6);
            if (s < 0) s = 0;
            return (s / 60).ToString("00", CultureInfo.InvariantCulture) + ":" + (s % 60).ToString("00", CultureInfo.InvariantCulture);
        }

        /// <summary>A survived duration "1:12" (minutes without padding, seconds rounded down).</summary>
        public static string Duration(double seconds)
        {
            if (double.IsNaN(seconds) || seconds < 0.0) seconds = 0.0;
            long s = (long)Math.Floor(seconds + 1e-6);
            return (s / 60).ToString(CultureInfo.InvariantCulture) + ":" + (s % 60).ToString("00", CultureInfo.InvariantCulture);
        }

        /// <summary>
        /// keyBase + ".one" or ".other" formatted with n. French uses the singular for 0 and 1, English only for 1.
        /// </summary>
        public static string Count(string keyBase, int n)
        {
            return Count(keyBase, n, Language);
        }

        public static string Count(string keyBase, int n, int language)
        {
            bool one = language == English ? n == 1 : (n == 0 || n == 1);
            return FormatIn(language, keyBase + (one ? ".one" : ".other"), n.ToString(CultureInfo.InvariantCulture));
        }

        /// <summary>"1er" / "2e" ... (EN "1st", "2nd"), "Ex æquo 1er" (EN "Tied 1st") when shared.</summary>
        public static string Rank(int rank, bool shared)
        {
            return Rank(rank, shared, Language);
        }

        public static string Rank(int rank, bool shared, int language)
        {
            if (rank < 1) rank = 1;
            string key = "results.rank." + rank.ToString(CultureInfo.InvariantCulture);
            string r = Has(key, language)
                ? Get(key, language)
                : FormatIn(language, "results.rank.n", rank.ToString(CultureInfo.InvariantCulture));
            return shared ? FormatIn(language, "results.tied", r) : r;
        }

        /// <summary>The displayed name of a sim player: "Toi" for the human, else the name of its displayed color.</summary>
        public static string PlayerName(int playerIndex, int humanIndex)
        {
            if (playerIndex >= 0 && playerIndex == humanIndex) return Get(Palette.HumanNameKey);
            return Get(Palette.ColorNameKey(Palette.ColorIndexOf(playerIndex)));
        }

        private static string AreaNumber(double percent, int language)
        {
            if (double.IsNaN(percent) || double.IsInfinity(percent)) percent = 0.0;
            if (percent < 0.0) percent = 0.0;
            double r1 = Math.Round(percent, 1, MidpointRounding.AwayFromZero);
            return r1 < 10.0 ? Decimal(r1, 1, language) : Decimal(percent, 0, language);
        }
    }
}
