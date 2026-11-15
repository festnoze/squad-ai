using System.Collections.Generic;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Meuble.Core
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
    /// M5 (docs/CONTRACT_M5_v3.md 6 and 15.7): the save file content, { "version": 1, "won": [...], "best": {...} }.
    /// Pure data and rules; the file handling (paths, atomic writes, the .bak and .bad files) is SaveStore (Runtime).
    /// </summary>
    public sealed class SaveData
    {
        public const int CurrentVersion = 1;

        [JsonProperty("version")] public int Version = CurrentVersion;
        [JsonProperty("won")] public List<string> Won = new List<string>();
        [JsonProperty("best")] public Dictionary<string, float> Best = new Dictionary<string, float>();

        /// <summary>
        /// Records a win: the level joins Won (once), and its best time is replaced only by a strictly lower one. A null or
        /// empty level id records nothing.
        /// </summary>
        public RecordResult RecordWin(string levelId, float seconds)
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
            if (Best.TryGetValue(levelId, out float previous))
            {
                result.PreviousBest = previous;
                if (seconds < previous) // MUTATION:BEST_TIME
                {
                    Best[levelId] = seconds;
                    result.NewBest = true;
                }
            }
            else
            {
                Best[levelId] = seconds;
                result.NewBest = true;
            }
            result.Best = Best[levelId];
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
