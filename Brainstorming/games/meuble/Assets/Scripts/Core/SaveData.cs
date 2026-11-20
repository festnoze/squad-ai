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

        /// <summary>M7 1.4: the tier a save without a quality choice gets, Moyen on a mobile platform, Haut on PC.</summary>
        public static string DefaultQuality(bool mobile) => mobile ? QualityMedium : QualityHigh; // MUTATION:QUALITY_PLATFORM_DEFAULT

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
        // one of WallOpacitySteps. A missing field or an unknown value is Lowered and Tuning.WallOpacityDefault: the version
        // stays 1 and every older save loads lowered at 20 %. Product owner, 2026-11-19: the default briefly went from
        // "lowered" to "both", then back to "lowered" the same day. The "walls" key is always written, so a save that holds
        // it (even "both") keeps it as an explicit choice; only a save without the key (written before the walls pass)
        // takes the default.
        public const string WallsLowered = "lowered";
        public const string WallsSeeThrough = "seethrough";
        public const string WallsBoth = "both";
        public const string WallsNone = "none";

        /// <summary>The wall opacities the Opacité des murs / Wall opacity row cycles through, in percent.</summary>
        public static readonly int[] WallOpacitySteps = { 10, 20, 35, 50 };

        [JsonProperty("walls")] public string Walls = WallsLowered;
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
                Walls = IsWalls(Walls) ? Walls : WallsLowered, // MUTATION:OPTIONS_WALLS_FALLBACK
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
    /// M5 (docs/CONTRACT_M5_v3.md 6 and 15.7): the save file content, { "version": 1, "won": [...], "best": {...} }.
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
        /// Records a win: the level joins Won (once), and its best time is replaced only by a strictly lower one. A null or
        /// empty level id records nothing.
        /// </summary>
        public RecordResult RecordWin(string levelId, float seconds)
        {
            return RecordWin(levelId, seconds, DifficultyDef.Normal);
        }

        /// <summary>
        /// M7 design (docs/CONTRACT_M7.md 4.1): a win at <paramref name="difficulty"/>. The level joins Won whatever the
        /// difficulty (unlocking is per level); the best time is kept under <see cref="DifficultyDef.RecordKey"/>: the bare
        /// id at Normal (old saves keep their records), "levelN@facile" and "levelN@difficile" otherwise.
        /// </summary>
        public RecordResult RecordWin(string levelId, float seconds, string difficulty)
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
            string key = DifficultyDef.RecordKey(levelId, difficulty);
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

        /// <summary>Level index i of the play order is unlocked when i is 0 or the level at i - 1 is won.</summary>
        public bool IsUnlocked(IReadOnlyList<string> order, int index)
        {
            if (order == null || index < 0 || index >= order.Count)
            {
                return false;
            }
            return index == 0 || (Won != null && Won.Contains(order[index - 1]));
        }

        /// <summary>
        /// Parses a save. Returns null and a problem on any failure, and never throws (CONTRACT_M5_v3 15.7):
        /// <list type="bullet">
        /// <item>not JSON, or not a JSON object;</item>
        /// <item>a missing <c>version</c>, a non-integer one, 0 or below, or above <see cref="CurrentVersion"/>;</item>
        /// <item>a <c>won</c> that is not a list of strings, a <c>best</c> that is not an object of finite, non-negative
        /// numbers.</item>
        /// </list>
        /// A missing <c>won</c> or <c>best</c> is an empty one, and a level listed twice in <c>won</c> is kept once.
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

        public string ToJson() => JsonConvert.SerializeObject(this, Formatting.Indented);
    }
}
