using System.Collections.Generic;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace OutOfSight.Core
{
    /// <summary>The outcome of recording a win (docs/CONTRACT_M5_v3.md section 6).</summary>
    public struct RecordResult
    {
        public float Best;
        public bool NewBest;
        /// <summary>The best time before this win, or a negative value when there was none.</summary>
        public float PreviousBest;
    }

    /// <summary>
    /// M6 (docs/CONTRACT_M6.md 2.1): the player's options, saved as SaveData.options (version stays 1: a missing
    /// object means <see cref="Default"/>, so an old save loads unchanged). Every field is independently clamped to
    /// its own range and step by <see cref="Clamped"/>, so a hand edited or out of range value behaves predictably
    /// instead of rejecting the whole save: unlike <see cref="SaveData"/> itself, a malformed options object never
    /// fails the load, it only falls back to defaults.
    /// </summary>
    public sealed class SaveOptions
    {
        public const string ConeAlways = "always";
        public const string ConeNever = "never";

        [JsonProperty("sensitivity")] public float Sensitivity = Tuning.SensitivityDefault;
        [JsonProperty("volume")] public int Volume = Tuning.VolumeDefault;
        [JsonProperty("cone")] public string Cone = ConeAlways;

        // Audio overhaul (docs/audio/AUDIO_REPORT.md 5): the music's own level, a percentage under the Volume. A missing field
        // (every save before it) is Tuning.MusicDefault: the version stays 1 and an older save loads as is.
        [JsonProperty("music")] public int Music = Tuning.MusicDefault;

        // M7 (docs/CONTRACT_M7.md 1.4): the quality tier, "low" (Bas), "medium" (Moyen) or "high" (Haut). Null, a missing
        // field or an unknown value is the platform default (QualityFor): the version stays 1 and an M6 save loads as is.
        public const string QualityLow = "low";
        public const string QualityMedium = "medium";
        public const string QualityHigh = "high";

        [JsonProperty("quality", NullValueHandling = NullValueHandling.Ignore)] public string Quality;

        /// <summary>
        /// M7 1.4: the tier a save without a quality choice gets. Haut on every platform since 2026-11-25 (user request; it
        /// was Moyen on mobile). <paramref name="mobile"/> is kept so a platform split can come back without touching callers.
        /// </summary>
        public static string DefaultQuality(bool mobile) => QualityHigh;

        /// <summary>True for "low", "medium" and "high".</summary>
        public static bool IsQuality(string value) => value == QualityLow || value == QualityMedium || value == QualityHigh;

        /// <summary>M7 1.4: the saved tier, or the platform default when there is none (or it is not a known tier).</summary>
        public string QualityFor(bool mobile) => IsQuality(Quality) ? Quality : DefaultQuality(mobile);

        /// <summary>The Qualité button's cycle: Bas, Moyen, Haut, then Bas again (anything else starts at Bas).</summary>
        public static string NextQuality(string quality) =>
            quality == QualityLow ? QualityMedium : quality == QualityMedium ? QualityHigh : QualityLow;

        // M7 design (docs/CONTRACT_M7.md 4.1): the difficulty, "facile", "normal" or "difficile" (DifficultyDef ids). Null, a
        // missing field or an unknown value is Normal: the version stays 1 and an M6 save loads as is.
        [JsonProperty("difficulty", NullValueHandling = NullValueHandling.Ignore)] public string Difficulty;

        /// <summary>M7 design: the saved difficulty id, Normal when there is none (or it is not a known id).</summary>
        [JsonIgnore] public string DifficultyId => DifficultyDef.Normalize(Difficulty);

        // The language of every shown string, "en" (English) or "fr" (French). Null, a missing field or an unknown value is
        // English: the version stays 1 and an older save loads as is.
        [JsonProperty("language", NullValueHandling = NullValueHandling.Ignore)] public string Language;

        /// <summary>The saved language, English when there is none (or it is not a known one).</summary>
        [JsonIgnore] public string LanguageId => Strings.NormalizeLanguage(Language);

        // M7 walls pass (product owner, 2026-11-19): how a wall between the camera and the player gets out of the way:
        // "lowered" (it sinks to a low stub, its doorways standing), "seethrough" (it fades to WallOpacity), "both" (the stub
        // stays and the wall above it fades to WallOpacity) or "none" (the walls never change). WallOpacity is a percentage,
        // one of WallOpacitySteps. A missing field or an unknown value is Both and Tuning.WallOpacityDefault (10 %): the
        // version stays 1. Product owner, 2026-11-19: the default briefly went from "lowered" to "both", then back to
        // "lowered" the same day; product owner, 2026-11-20: the default is "both" at 10 % (new saves, Par defaut, and a save
        // without the key or with an unknown value). The "walls" and "wallOpacity" keys are always written, so a save that
        // holds them (even "lowered" at 20 %, the old defaults) keeps them as an explicit choice; only a save without the
        // key (written before the walls pass) takes the default.
        public const string WallsLowered = "lowered";
        public const string WallsSeeThrough = "seethrough";
        public const string WallsBoth = "both";
        public const string WallsNone = "none";

        /// <summary>The wall opacities the Opacité des murs / Wall opacity row cycles through, in percent.</summary>
        public static readonly int[] WallOpacitySteps = { 10, 20, 35, 50 };

        [JsonProperty("walls")] public string Walls = WallsBoth;
        [JsonProperty("wallOpacity")] public int WallOpacity = Tuning.WallOpacityDefault;

        /// <summary>True for "lowered", "seethrough", "both" and "none".</summary>
        public static bool IsWalls(string value) => value == WallsLowered || value == WallsSeeThrough || value == WallsBoth || value == WallsNone;

        /// <summary>The Murs / Walls row's cycle: Lowered, See-through, Both, None, then Lowered again.</summary>
        public static string NextWalls(string walls) =>
            walls == WallsLowered ? WallsSeeThrough : walls == WallsSeeThrough ? WallsBoth : walls == WallsBoth ? WallsNone : WallsLowered;

        /// <summary>The Wall opacity row's cycle: the next of <see cref="WallOpacitySteps"/>, then the first again.</summary>
        public static int NextWallOpacity(int percent)
        {
            for (int i = 0; i < WallOpacitySteps.Length; i++)
            {
                if (WallOpacitySteps[i] > percent)
                {
                    return WallOpacitySteps[i];
                }
            }
            return WallOpacitySteps[0];
        }

        /// <summary>The step of <see cref="WallOpacitySteps"/> nearest to <paramref name="percent"/>.</summary>
        public static int NearestWallOpacity(int percent)
        {
            int best = Tuning.WallOpacityDefault;
            int gap = int.MaxValue;
            foreach (int step in WallOpacitySteps)
            {
                if (Mathf.Abs(step - percent) < gap)
                {
                    gap = Mathf.Abs(step - percent);
                    best = step;
                }
            }
            return best;
        }

        /// <summary>True when the walls' opacity is used: the see-through and the both modes.</summary>
        [JsonIgnore] public bool WallOpacityApplies => Walls == WallsSeeThrough || Walls == WallsBoth;

        /// <summary>"Jamais": VisionConeView hides the floor cones; the eye indicator and the screen edge pulse are unaffected.</summary>
        public bool HidesCone => Cone == ConeNever;

        public static SaveOptions Default() => new SaveOptions();

        /// <summary>A copy with every field inside its range and on its step; an unrecognised Cone falls back to "always".</summary>
        public SaveOptions Clamped()
        {
            return new SaveOptions
            {
                Sensitivity = ClampStep(Sensitivity, Tuning.SensitivityMin, Tuning.SensitivityMax, Tuning.SensitivityStep),
                Volume = Mathf.RoundToInt(ClampStep(Volume, Tuning.VolumeMin, Tuning.VolumeMax, Tuning.VolumeStep)),
                Music = Mathf.RoundToInt(ClampStep(Music, Tuning.MusicMin, Tuning.MusicMax, Tuning.MusicStep)),
                Cone = Cone == ConeNever ? ConeNever : ConeAlways, // MUTATION:OPTIONS_CONE_FALLBACK
                Quality = IsQuality(Quality) ? Quality : null,
                Difficulty = DifficultyDef.Normalize(Difficulty) == Difficulty ? Difficulty : null, // MUTATION:OPTIONS_DIFFICULTY_FALLBACK
                Language = Language == Strings.English || Language == Strings.French ? Language : null,
                Walls = IsWalls(Walls) ? Walls : WallsBoth, // MUTATION:OPTIONS_WALLS_FALLBACK
                WallOpacity = NearestWallOpacity(WallOpacity),
            };
        }

        private static float ClampStep(float value, float min, float max, float step)
        {
            if (float.IsNaN(value) || float.IsInfinity(value))
            {
                value = min;
            }
            float clamped = Mathf.Clamp(value, min, max);
            float steps = Mathf.Round((clamped - min) / step); // MUTATION:OPTIONS_STEP_ROUND
            return min + steps * step;
        }

        /// <summary>
        /// Parses the "options" object defensively: missing, not an object, or a field of the wrong type keeps that
        /// field's default; every field is then <see cref="Clamped"/>. Never throws.
        /// </summary>
        public static SaveOptions Parse(JToken token)
        {
            var options = Default();
            if (!(token is JObject obj))
            {
                return options;
            }
            JToken s = obj["sensitivity"];
            if (s != null && (s.Type == JTokenType.Float || s.Type == JTokenType.Integer))
            {
                options.Sensitivity = s.Value<float>();
            }
            JToken v = obj["volume"];
            if (v != null && (v.Type == JTokenType.Float || v.Type == JTokenType.Integer))
            {
                options.Volume = (int)v.Value<float>();
            }
            JToken m = obj["music"];
            if (m != null && (m.Type == JTokenType.Float || m.Type == JTokenType.Integer))
            {
                options.Music = (int)m.Value<float>();
            }
            JToken c = obj["cone"];
            if (c != null && c.Type == JTokenType.String)
            {
                options.Cone = c.Value<string>();
            }
            JToken q = obj["quality"];
            if (q != null && q.Type == JTokenType.String)
            {
                options.Quality = q.Value<string>();
            }
            JToken d = obj["difficulty"];
            if (d != null && d.Type == JTokenType.String)
            {
                options.Difficulty = d.Value<string>();
            }
            JToken l = obj["language"];
            if (l != null && l.Type == JTokenType.String)
            {
                options.Language = l.Value<string>();
            }
            JToken w = obj["walls"];
            if (w != null && w.Type == JTokenType.String)
            {
                options.Walls = w.Value<string>();
            }
            JToken wo = obj["wallOpacity"];
            if (wo != null && (wo.Type == JTokenType.Float || wo.Type == JTokenType.Integer))
            {
                options.WallOpacity = Mathf.RoundToInt(wo.Value<float>());
            }
            return options.Clamped();
        }
    }

    /// <summary>
    /// M5 (docs/CONTRACT_M5_v3.md 6 and 15.7): the save file content, { "version": 1, "won": [...], "best": {...} }; levels
    /// v2 (docs/levels_v2/LEVELS_V2.md 7) adds "unlocked" and "order" with the version still 1.
    /// Pure data and rules; the file handling (paths, atomic writes, the .bak and .bad files) is SaveStore (Runtime).
    /// </summary>
    public sealed class SaveData
    {
        public const int CurrentVersion = 1;

        [JsonProperty("version")] public int Version = CurrentVersion;
        [JsonProperty("won")] public List<string> Won = new List<string>();
        [JsonProperty("best")] public Dictionary<string, float> Best = new Dictionary<string, float>();
        /// <summary>M6 (docs/CONTRACT_M6.md 2.1): missing on an old save, which then loads with <see cref="SaveOptions.Default"/>.</summary>
        [JsonProperty("options")] public SaveOptions Options = SaveOptions.Default();

        /// <summary>
        /// Levels v2 (docs/levels_v2/LEVELS_V2.md 7): the levels the one-shot order migration opened (<see cref="MigrateOrder"/>),
        /// each playable whatever its predecessor in the play order. Missing on an older save, which then reads it as empty
        /// (the version stays 1); a value that is not a list of strings is a parse problem, like <c>won</c>.
        /// </summary>
        [JsonProperty("unlocked")] public List<string> Unlocked = new List<string>();

        /// <summary>
        /// Levels v2: the manifest revision this save's progress was migrated to (levels.json "rev"). Missing, not an integer
        /// or below 1 reads as 1, the v1 play order. SaveStore stamps a fresh save with the current revision.
        /// </summary>
        [JsonProperty("order")] public int Order = 1;

        /// <summary>
        /// Onboarding tips (idea 3, docs/next/progress/TIPS.md): the keys of the first-time tips already shown (tips.*), each
        /// shown once per save. Missing, null or malformed reads as empty and never fails the save (a player loses at most a
        /// tip again). "Par défaut" resets the options only: the tips stay shown; only a new save shows them again.
        /// </summary>
        [JsonProperty("tips")] public List<string> Tips = new List<string>();

        /// <summary>
        /// Stars (idea 5, docs/next/progress/STARS.md): the best star count (1 to <see cref="Tuning.StarsPerLevel"/>) per
        /// record key (<see cref="DifficultyDef.RecordKey"/> of the level's RecordId: a redesigned level starts its stars
        /// again, as its records). Missing on an older save, which reads it as empty (version stays 1): a level never won
        /// since has 0 stars. Never fails a load: a malformed object or entry is skipped (<see cref="Parse"/>).
        /// </summary>
        [JsonProperty("stars")] public Dictionary<string, int> Stars = new Dictionary<string, int>();

        /// <summary>
        /// ADSSHOP (docs/next/progress/ADSSHOP.md): the shop purchases (owned products, granted entitlements, consumable
        /// counts). Missing on an older save, which reads it as empty (version stays 1); never fails a load
        /// (<see cref="SavePurchases.Parse"/>).
        /// </summary>
        [JsonProperty("purchases")] public SavePurchases Purchases = new SavePurchases();

        /// <summary>
        /// Stars: records <paramref name="stars"/> for <paramref name="recordId"/> at <paramref name="difficulty"/>, kept only
        /// when above the saved count (clamped to 0..<see cref="Tuning.StarsPerLevel"/>). Returns the count now saved; 0 for
        /// a null or empty record id. Does not save: the caller's RecordWin write (SaveStore) carries it.
        /// </summary>
        public int RecordStars(string recordId, int stars, string difficulty)
        {
            if (string.IsNullOrEmpty(recordId))
            {
                return 0;
            }
            Stars = Stars ?? new Dictionary<string, int>();
            int clamped = Mathf.Clamp(stars, 0, Tuning.StarsPerLevel);
            string key = DifficultyDef.RecordKey(recordId, difficulty);
            if (!Stars.TryGetValue(key, out int previous) || clamped > previous) // MUTATION:STARS_ONLY_UP
            {
                Stars[key] = clamped;
                return clamped;
            }
            return previous;
        }

        /// <summary>Stars: the saved count for <paramref name="recordId"/> at <paramref name="difficulty"/>, 0 when none.</summary>
        public int StarsOf(string recordId, string difficulty)
        {
            if (string.IsNullOrEmpty(recordId) || Stars == null)
            {
                return 0;
            }
            return Stars.TryGetValue(DifficultyDef.RecordKey(recordId, difficulty), out int stars) ? stars : 0;
        }

        /// <summary>
        /// Records a win: the level joins Won (once), and its best time is replaced only by a strictly lower one. A null or
        /// empty level id records nothing.
        /// </summary>
        public RecordResult RecordWin(string levelId, float seconds)
        {
            return RecordWin(levelId, levelId, seconds, DifficultyDef.Normal);
        }

        /// <summary>
        /// M7 design (docs/CONTRACT_M7.md 4.1): a win at <paramref name="difficulty"/>. The level joins Won whatever the
        /// difficulty (unlocking is per level); the best time is kept under <see cref="DifficultyDef.RecordKey"/>: the bare
        /// id at Normal (old saves keep their records), "levelN@facile" and "levelN@difficile" otherwise.
        /// </summary>
        public RecordResult RecordWin(string levelId, float seconds, string difficulty)
        {
            return RecordWin(levelId, levelId, seconds, difficulty);
        }

        /// <summary>
        /// Levels v2 (LEVELS_V2.md 7, record revision): a win of <paramref name="levelId"/> whose record is kept under
        /// <paramref name="recordId"/> (<see cref="LevelDef.RecordId"/>, "level6~1" for a redesigned level). Won gets the bare
        /// level id (unlocking is unaffected by a revision); Best gets <see cref="DifficultyDef.RecordKey"/>(recordId,
        /// difficulty), so a record made on an older version of the level is never read again (it stays in the file). A null
        /// or empty record id falls back to the level id.
        /// </summary>
        public RecordResult RecordWin(string levelId, string recordId, float seconds, string difficulty)
        {
            var result = new RecordResult { PreviousBest = -1f };
            if (string.IsNullOrEmpty(levelId))
            {
                return result;
            }
            Won = Won ?? new List<string>();
            Best = Best ?? new Dictionary<string, float>();
            if (!Won.Contains(levelId))
            {
                Won.Add(levelId);
            }
            string key = DifficultyDef.RecordKey(string.IsNullOrEmpty(recordId) ? levelId : recordId, difficulty);
            if (Best.TryGetValue(key, out float previous))
            {
                result.PreviousBest = previous;
                if (seconds < previous) // MUTATION:BEST_TIME
                {
                    Best[key] = seconds;
                    result.NewBest = true;
                }
            }
            else
            {
                Best[key] = seconds;
                result.NewBest = true;
            }
            result.Best = Best[key];
            return result;
        }

        /// <summary>
        /// Levels v2 (LEVELS_V2.md 7): level index i of the play order is playable when i is 0, or the level itself is won (a
        /// won level never locks again after a reorder), or the level at i - 1 is won, or the order migration opened it
        /// (<see cref="Unlocked"/>). False for a null order or an index outside it.
        /// </summary>
        public bool IsUnlocked(IReadOnlyList<string> order, int index)
        {
            if (order == null || index < 0 || index >= order.Count)
            {
                return false;
            }
            if (index == 0)
            {
                return true;
            }
            string id = order[index];
            if (Won != null && Won.Contains(id)) // MUTATION:UNLOCK_WON
            {
                return true;
            }
            if (Won != null && Won.Contains(order[index - 1]))
            {
                return true;
            }
            return Unlocked != null && Unlocked.Contains(id); // MUTATION:UNLOCK_MIGRATED
        }

        /// <summary>
        /// Levels v2 (LEVELS_V2.md 7): the one-shot migration of the progress to manifest revision <paramref name="rev"/>.
        /// Nothing happens (false) when <see cref="Order"/> is already <paramref name="rev"/> or above. Otherwise every id of
        /// <paramref name="previous"/> (the play order of the revision before) that was playable under the previous rule
        /// (index 0, or its predecessor in <paramref name="previous"/> won) and is still listed in <paramref name="current"/>
        /// joins <see cref="Unlocked"/>, then Order becomes rev (true). An id already won is skipped (the won term of
        /// <see cref="IsUnlocked"/> opens it forever), and an id is never listed twice. Won and Best are never touched.
        /// </summary>
        public bool MigrateOrder(int rev, IReadOnlyList<string> previous, IReadOnlyList<string> current)
        {
            if (Order >= rev)
            {
                return false;
            }
            Won = Won ?? new List<string>();
            Unlocked = Unlocked ?? new List<string>();
            if (previous != null && current != null)
            {
                for (int j = 0; j < previous.Count; j++)
                {
                    string id = previous[j];
                    if (string.IsNullOrEmpty(id) || Won.Contains(id) || Unlocked.Contains(id) || !Listed(current, id))
                    {
                        continue;
                    }
                    bool playable = j == 0 || Won.Contains(previous[j - 1]); // MUTATION:MIGRATE_PREDECESSOR
                    if (playable)
                    {
                        Unlocked.Add(id);
                    }
                }
            }
            Order = rev;
            return true;
        }

        private static bool Listed(IReadOnlyList<string> list, string id)
        {
            for (int i = 0; i < list.Count; i++)
            {
                if (list[i] == id)
                {
                    return true;
                }
            }
            return false;
        }

        /// <summary>
        /// Parses a save. Returns null and a problem on any failure, and never throws (CONTRACT_M5_v3 15.7):
        /// <list type="bullet">
        /// <item>not JSON, or not a JSON object;</item>
        /// <item>a missing <c>version</c>, a non-integer one, 0 or below, or above <see cref="CurrentVersion"/>;</item>
        /// <item>a <c>won</c> or an <c>unlocked</c> that is not a list of strings, a <c>best</c> that is not an object of
        /// finite, non-negative numbers.</item>
        /// </list>
        /// A missing <c>won</c>, <c>unlocked</c> or <c>best</c> is an empty one, a level listed twice is kept once, and a
        /// missing or malformed <c>order</c> reads as 1.
        /// </summary>
        public static SaveData Parse(string json, out string problem)
        {
            problem = null;
            try
            {
                if (string.IsNullOrWhiteSpace(json))
                {
                    problem = "empty";
                    return null;
                }
                if (!(JToken.Parse(json) is JObject root))
                {
                    problem = "not a JSON object";
                    return null;
                }
                JToken version = root["version"];
                if (version == null || version.Type != JTokenType.Integer)
                {
                    problem = "missing version";
                    return null;
                }
                long v = version.Value<long>();
                if (v <= 0 || v > CurrentVersion)
                {
                    problem = "version " + v;
                    return null;
                }
                var data = new SaveData { Version = (int)v };
                JToken won = root["won"];
                if (won != null && won.Type != JTokenType.Null)
                {
                    if (!(won is JArray list))
                    {
                        problem = "won is not a list";
                        return null;
                    }
                    foreach (JToken id in list)
                    {
                        if (id.Type != JTokenType.String)
                        {
                            problem = "won holds a " + id.Type;
                            return null;
                        }
                        string s = id.Value<string>();
                        if (!string.IsNullOrEmpty(s) && !data.Won.Contains(s))
                        {
                            data.Won.Add(s);
                        }
                    }
                }
                JToken best = root["best"];
                if (best != null && best.Type != JTokenType.Null)
                {
                    if (!(best is JObject times))
                    {
                        problem = "best is not an object";
                        return null;
                    }
                    foreach (JProperty p in times.Properties())
                    {
                        if (p.Value.Type != JTokenType.Float && p.Value.Type != JTokenType.Integer)
                        {
                            problem = "best " + p.Name + " is a " + p.Value.Type;
                            return null;
                        }
                        double seconds = p.Value.Value<double>();
                        if (double.IsNaN(seconds) || double.IsInfinity(seconds) || seconds < 0.0 || seconds > float.MaxValue)
                        {
                            problem = "best " + p.Name + " is " + seconds;
                            return null;
                        }
                        data.Best[p.Name] = (float)seconds;
                    }
                }
                // Levels v2 (LEVELS_V2.md 7): "unlocked" follows the rules of "won" (missing or null is empty, anything but a
                // list of strings is a problem, an id listed twice is kept once); "order" never fails the save.
                JToken unlocked = root["unlocked"];
                if (unlocked != null && unlocked.Type != JTokenType.Null)
                {
                    if (!(unlocked is JArray opened))
                    {
                        problem = "unlocked is not a list";
                        return null;
                    }
                    foreach (JToken id in opened)
                    {
                        if (id.Type != JTokenType.String)
                        {
                            problem = "unlocked holds a " + id.Type;
                            return null;
                        }
                        string s = id.Value<string>();
                        if (!string.IsNullOrEmpty(s) && !data.Unlocked.Contains(s))
                        {
                            data.Unlocked.Add(s);
                        }
                    }
                }
                data.Order = ParseOrder(root["order"]);
                // Stars (idea 5): never fails the save. Missing, null or not an object reads as empty; an entry that is not an
                // integer is skipped; a value outside 0..StarsPerLevel is clamped (a hand edited save keeps its other stars).
                if (root["stars"] is JObject stars)
                {
                    foreach (JProperty p in stars.Properties())
                    {
                        if (p.Value.Type == JTokenType.Integer && !string.IsNullOrEmpty(p.Name))
                        {
                            long count = p.Value.Value<long>();
                            data.Stars[p.Name] = (int)System.Math.Max(0, System.Math.Min(Tuning.StarsPerLevel, count));
                        }
                    }
                }
                // Onboarding tips (idea 3): the shown keys; anything but a list of strings is ignored, never a problem.
                if (root["tips"] is JArray tips)
                {
                    foreach (JToken id in tips)
                    {
                        string s = id.Type == JTokenType.String ? id.Value<string>() : null;
                        if (!string.IsNullOrEmpty(s) && !data.Tips.Contains(s))
                        {
                            data.Tips.Add(s);
                        }
                    }
                }
                // ADSSHOP: the purchases never fail the save either (a malformed object reads as nothing bought).
                data.Purchases = SavePurchases.Parse(root["purchases"]);
                // M6 (CONTRACT_M6 2.1): missing, malformed or absent entirely, this never fails the save (SaveOptions.Parse
                // falls back to defaults field by field instead of rejecting the whole file).
                data.Options = SaveOptions.Parse(root["options"]);
                return data;
            }
            catch (System.Exception e)
            {
                problem = e.GetType().Name + ": " + e.Message;
                return null;
            }
        }

        /// <summary>Levels v2: the saved order revision; missing, not an integer or below 1 reads as 1.</summary>
        private static int ParseOrder(JToken token)
        {
            if (token == null || token.Type != JTokenType.Integer)
            {
                return 1;
            }
            long value = token.Value<long>();
            return value < 1 || value > int.MaxValue ? 1 : (int)value;
        }

        public string ToJson() => JsonConvert.SerializeObject(this, Formatting.Indented);
    }
}
